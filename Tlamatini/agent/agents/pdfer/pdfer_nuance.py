# ═══════════════════════════════════════════════════════════════════
#   ✦  T L A M A T I N I  ✦   —   "one who knows"
#
#   Created by  Angela López Mendoza   ·   @angelahack1
#   Developer · Architect · Creator of Tlamatini
#
#   Every line of this file was written by Angela López Mendoza.
# ═══════════════════════════════════════════════════════════════════
#   Tlamatini Author Banner — do not remove (releases scrub the name automatically)
"""PDFer nuance engine — reading the content BEFORE choosing how to dress it.

WHAT ANGELA ASKED FOR
---------------------
    *"create on it a new nuance detection so based in the content — style,
    font, color, background, images, etc — must be calculated BEFORE the
    document crafting. For example if the content is detected to be of
    science and technology the background must be set to black and the
    foreground font white with gradients … if the file has an abstract and it
    seems to be a paper, then white background and black font, and LaTeX
    100% styled."*

That is a **classifier**, and this module is it. It answers one question —
*what kind of document is this?* — and hands the answer to `pdfer_theme`,
which turns it into colour, type, spacing and ornament. Nothing here draws
anything; nothing in the theme layer reads the content. That separation is
deliberate: it is what lets the classification be tested on its own, and what
lets `nuance='paper'` from a chat prompt bypass detection entirely without
touching any rendering code.

HOW IT DECIDES  (and why it is not just a keyword list)
--------------------------------------------------------
Three independent evidence families vote, and they are weighted differently
on purpose:

1. **STRUCTURE — the strongest signal.** A document with an *Abstract*, a
   *Methods* section and a *References* list is an academic paper even if it
   never says the word "research". IMRaD headings, citation shapes
   (``[12]``, ``(Smith et al., 2023)``), a DOI, an arXiv id, numbered legal
   clauses, an ingredients list — these are near-decisive because a human
   only ever produces them on purpose. Structure therefore carries roughly
   **triple** the weight of vocabulary.

2. **LEXICON — the broad signal.** Weighted term lists per domain, matched on
   word boundaries. Counts are **log-damped** (``1 + ln(n)``) so a document
   that says "quantum" fifty times does not out-vote one that says
   "plaintiff", "defendant", "hereinafter" and "shall" five times each.
   Breadth of evidence beats repetition, which is how a human reads too.

3. **REGISTER — the tie-breaker.** Sentence length, passive constructions,
   first/second-person address, imperatives, exclamation density. This is
   what separates a *marketing brochure* from a *product manual* when both
   talk about the same product in the same words.

A verdict is only accepted when it clears the runner-up by a margin; a narrow
win is reported as low confidence, and the theme layer answers low confidence
by dressing the document more conservatively. **An uncertain classifier that
knows it is uncertain is safe; a confident wrong one is not.**

THE DECORATION BUDGET  (Angela: *"if it knows that is plenty safe"*)
--------------------------------------------------------------------
Every verdict carries `decoration_budget` — how much ornament this content can
*bear*. It is not an aesthetic slider; it is a safety judgement:

* A **legal instrument**, a **medical dosage table** or a **financial
  statement** gets ``none``. Decorating a contract makes it look forged, and
  decorating a drug chart is genuinely dangerous.
* An **academic paper** gets ``restrained`` — a rule under the title and
  nothing else, because that is what a journal does.
* A **marketing brochure** gets ``rich``.

The budget is also lowered by low confidence and by content that looks like
it contains an *instruction the reader must follow exactly*. When PDFer is
unsure what it is holding, it decorates less.

CONTRACTS (do NOT weaken)
-------------------------
1. **NEVER RAISES.** `classify()` returns a verdict for any input at all —
   empty string, 40 MB of base64, binary junk. An unclassifiable document is
   ``minimal_note`` with confidence 0.0, which is a perfectly good answer.
2. **NEVER MUTATES THE CONTENT.** This module only reads.
3. **DETERMINISTIC.** No model call, no randomness. The same text always
   yields the same verdict, which is what makes it testable and what makes
   the optional LLM consultation in `pdfer_consult` an *override* rather than
   a dependency.
4. **CHEAP.** One pass to normalise, one regex sweep per family. A 500 kB
   document classifies in well under a tenth of a second, because this runs
   before every single render.

Author: Angela López Mendoza.
"""

from __future__ import annotations

import math
import re

__all__ = [
    "NUANCES",
    "NuanceVerdict",
    "classify",
    "detect_language",
    "normalise_nuance",
    "DECORATION_LEVELS",
]

DECORATION_LEVELS = ("none", "restrained", "moderate", "rich")


# ─────────────────────────────────────────────────────────────────────────
#  THE CATALOG
#
#  Each nuance declares what it IS, not how it looks — appearance lives in
#  `pdfer_theme`. ``aliases`` is what a human or an LLM might type into the
#  new ``nuance`` parameter; ``decoration`` is the safety ceiling described
#  above; ``prefers`` records the page character the theme layer should aim
#  for.
# ─────────────────────────────────────────────────────────────────────────
NUANCES = {
    "scientific_dark": {
        "label": "Science & technology",
        "summary": "Technical or scientific exposition — the dark, luminous "
                   "treatment Angela asked for by name.",
        "aliases": ("science", "scientific", "tech", "technology", "dark",
                    "engineering_dark", "physics", "chemistry", "astronomy",
                    "ai", "machine learning", "ciencia", "tecnologia",
                    "cientifico", "tecnológico"),
        "decoration": "rich",
        "prefers": {"dark": True, "pairing": "technical", "ratio": 1.25},
    },
    "academic_paper": {
        "label": "Academic paper",
        "summary": "A journal-shaped article: abstract, IMRaD sections, "
                   "citations, references. Typeset the way TeX would.",
        "aliases": ("paper", "academic", "journal", "thesis", "preprint",
                    "dissertation", "latex", "research", "article",
                    "articulo", "tesis", "paper academico"),
        "decoration": "restrained",
        "prefers": {"dark": False, "pairing": "scholarly", "ratio": 1.2},
    },
    "software_manual": {
        "label": "Software documentation",
        "summary": "API reference, runbook or developer guide — code is a "
                   "first-class citizen of the page.",
        "aliases": ("manual", "docs", "documentation", "api", "readme",
                    "software", "developer", "runbook", "sdk", "reference",
                    "documentacion", "manual tecnico"),
        "decoration": "moderate",
        "prefers": {"dark": False, "pairing": "technical_mono", "ratio": 1.25},
    },
    "engineering_spec": {
        "label": "Engineering specification",
        "summary": "Requirements, tolerances, part numbers and procedures. "
                   "Precision over personality.",
        "aliases": ("spec", "specification", "requirements", "datasheet",
                    "engineering", "hardware", "firmware", "mechanical",
                    "especificacion", "ingenieria"),
        "decoration": "restrained",
        "prefers": {"dark": False, "pairing": "technical", "ratio": 1.2},
    },
    "business_report": {
        "label": "Business report",
        "summary": "Status, strategy, performance. Restrained, evidential, "
                   "boardroom-legible.",
        "aliases": ("business", "report", "corporate", "management",
                    "quarterly", "executive", "status", "informe",
                    "reporte", "negocio", "empresarial"),
        "decoration": "moderate",
        "prefers": {"dark": False, "pairing": "corporate", "ratio": 1.25},
    },
    "financial_ledger": {
        "label": "Financial statement",
        "summary": "Figures that must line up on their units digit. Almost "
                   "all table, no ornament.",
        "aliases": ("financial", "finance", "accounting", "ledger", "budget",
                    "invoice", "balance", "audit", "tax", "financiero",
                    "contabilidad", "presupuesto", "factura"),
        "decoration": "none",
        "prefers": {"dark": False, "pairing": "dense", "ratio": 1.2},
    },
    "legal_instrument": {
        "label": "Legal instrument",
        "summary": "Contract, policy, terms, notice. Deliberately "
                   "unremarkable — it must look like every other one.",
        "aliases": ("legal", "contract", "agreement", "terms", "policy",
                    "licence", "license", "nda", "compliance", "statute",
                    "legal", "contrato", "convenio", "juridico", "clausula"),
        "decoration": "none",
        "prefers": {"dark": False, "pairing": "legal", "ratio": 1.15},
    },
    "medical_clinical": {
        "label": "Clinical / medical",
        "summary": "Patient-facing or clinical material. Clean, calm, and "
                   "never decorated over a dosage.",
        "aliases": ("medical", "clinical", "health", "patient", "diagnosis",
                    "pharma", "nursing", "medico", "clinico", "salud",
                    "paciente"),
        "decoration": "none",
        "prefers": {"dark": False, "pairing": "corporate", "ratio": 1.2},
    },
    "security_briefing": {
        "label": "Security assessment",
        "summary": "Pentest, recon or incident material — near-black with "
                   "alert-grade accents.",
        "aliases": ("security", "pentest", "infosec", "vulnerability",
                    "incident", "threat", "recon", "forensics", "ciso",
                    "seguridad", "pentesting", "vulnerabilidad"),
        "decoration": "moderate",
        "prefers": {"dark": True, "pairing": "technical_mono", "ratio": 1.25},
    },
    "data_analysis": {
        "label": "Data analysis",
        "summary": "Measurement, statistics, findings. Built around figures "
                   "and their uncertainty.",
        "aliases": ("data", "analysis", "statistics", "analytics", "metrics",
                    "dataset", "benchmark", "datos", "analisis",
                    "estadistica"),
        "decoration": "moderate",
        "prefers": {"dark": False, "pairing": "technical", "ratio": 1.25},
    },
    "editorial_feature": {
        "label": "Editorial feature",
        "summary": "Long-form journalism or essay — magazine cadence, a "
                   "drop cap, generous measure.",
        "aliases": ("editorial", "magazine", "essay", "feature", "column",
                    "journalism", "blog", "opinion", "ensayo", "articulo "
                    "de opinion", "cronica"),
        "decoration": "rich",
        "prefers": {"dark": False, "pairing": "editorial", "ratio": 1.333},
    },
    "creative_literary": {
        "label": "Literary / creative",
        "summary": "Fiction, poetry, narrative. Quiet type, generous air, "
                   "nothing that competes with the words.",
        "aliases": ("fiction", "novel", "story", "poetry", "poem", "literary",
                    "creative", "narrative", "screenplay", "novela",
                    "cuento", "poema", "literario", "relato"),
        "decoration": "moderate",
        "prefers": {"dark": False, "pairing": "literary", "ratio": 1.333},
    },
    "marketing_brochure": {
        "label": "Marketing / promotional",
        "summary": "Built to be seen before it is read. The one place where "
                   "loud is correct.",
        "aliases": ("marketing", "brochure", "promo", "promotional", "sales",
                    "pitch", "campaign", "advert", "landing", "mercadotecnia",
                    "publicidad", "folleto", "ventas"),
        "decoration": "rich",
        "prefers": {"dark": False, "pairing": "promotional", "ratio": 1.414},
    },
    "educational_course": {
        "label": "Teaching material",
        "summary": "Lessons, exercises, worked examples. Warm, high-contrast, "
                   "colour-coded callouts.",
        "aliases": ("course", "lesson", "tutorial", "教材", "教学", "teaching",
                    "education", "training", "workshop", "curriculum",
                    "curso", "leccion", "tutorial", "educativo", "taller"),
        "decoration": "rich",
        "prefers": {"dark": False, "pairing": "friendly", "ratio": 1.25},
    },
    "government_policy": {
        "label": "Government / policy",
        "summary": "Public-sector formality: neutral, numbered, unshowy.",
        "aliases": ("government", "policy", "public", "regulation",
                    "directive", "municipal", "ministry", "gobierno",
                    "politica publica", "reglamento", "normativa"),
        "decoration": "restrained",
        "prefers": {"dark": False, "pairing": "legal", "ratio": 1.2},
    },
    "historical_archive": {
        "label": "Historical / archival",
        "summary": "Chronicle, archive, biography — warm paper and old-style "
                   "faces.",
        "aliases": ("history", "historical", "archive", "chronicle",
                    "biography", "genealogy", "heritage", "historia",
                    "historico", "archivo", "cronica", "biografia"),
        "decoration": "moderate",
        "prefers": {"dark": False, "pairing": "literary", "ratio": 1.25},
    },
    "culinary_recipe": {
        "label": "Recipe / culinary",
        "summary": "Ingredients, quantities, method. Warm and appetising, "
                   "but the quantities stay unambiguous.",
        "aliases": ("recipe", "cooking", "culinary", "menu", "kitchen",
                    "baking", "receta", "cocina", "menu", "reposteria"),
        "decoration": "rich",
        "prefers": {"dark": False, "pairing": "friendly", "ratio": 1.25},
    },
    "personal_letter": {
        "label": "Personal correspondence",
        "summary": "A letter or note to a person. Intimate, simple, no "
                   "corporate furniture.",
        "aliases": ("letter", "correspondence", "personal", "note", "memo",
                    "carta", "nota", "personal"),
        "decoration": "restrained",
        "prefers": {"dark": False, "pairing": "literary", "ratio": 1.25},
    },
    "presentation_deck": {
        "label": "Presentation handout",
        "summary": "Big type, short lines, one idea per block.",
        "aliases": ("presentation", "deck", "slides", "keynote", "handout",
                    "presentacion", "diapositivas"),
        "decoration": "rich",
        "prefers": {"dark": True, "pairing": "promotional", "ratio": 1.414},
    },
    "minimal_note": {
        "label": "Plain note",
        "summary": "Nothing distinctive found. Correct, quiet, unopinionated "
                   "— the honest answer when the content says nothing about "
                   "itself.",
        "aliases": ("plain", "minimal", "none", "default", "note", "simple",
                    "neutral", "simple", "sencillo"),
        "decoration": "restrained",
        "prefers": {"dark": False, "pairing": "neutral", "ratio": 1.25},
    },
}


# ─────────────────────────────────────────────────────────────────────────
#  LEXICONS — weighted term lists
#
#  Weight 3 = near-diagnostic (a word essentially only used in this domain).
#  Weight 2 = strong. Weight 1 = supporting.
#  Spanish terms sit alongside English deliberately: Angela writes in both,
#  and a Spanish technical report must classify as technical.
# ─────────────────────────────────────────────────────────────────────────
_LEXICON = {
    # ⚠️ BREADTH IS THE POINT HERE (widened 2026-09-06 after a measured miss).
    # The first draft of this lexicon was quantum-mechanics-only — "quantum,
    # entropy, photon, hamiltonian" — so an article about TOKAMAK PLASMA
    # CONFINEMENT matched NOTHING, scored zero lexical support, and was
    # classified as an engineering specification on the strength of its SI
    # units alone. It would have been dressed as a parts list.
    #
    # "Science and technology" is not one vocabulary, it is a dozen: plasma
    # physics, materials, optics, astronomy, aerospace, biology, chemistry,
    # computing, electronics. A classifier for the domain Angela named FIRST
    # has to actually know the domain, so all of them are represented.
    "scientific_dark": {
        3: ("quantum", "entropy", "photon", "electron", "hamiltonian",
            "eigenvalue", "thermodynamic", "relativistic", "catalysis",
            "spectroscopy", "nanoscale", "qubit", "isotope", "molecular",
            "wavelength", "plasma", "tokamak", "toroidal", "poloidal",
            "cyclotron", "superconduct", "deuterium", "tritium", "neutrino",
            "quark", "boson", "fermion", "spintronic", "photovoltaic",
            "piezoelectric", "ferromagnet", "antiferromagnet", "perovskite",
            "graphene", "crystallograph", "diffraction", "interferomet",
            "gravitational wave", "exoplanet", "nucleosynthesis",
            "cuantico", "termodinamic", "espectroscopia", "plasma"),
        2: ("experiment", "hypothesis", "theory", "measurement", "coefficient",
            "velocity", "magnitude", "simulation", "algorithm", "neural",
            "gradient", "topology", "kinetics", "amplitude", "frequency",
            "voltage", "semiconductor", "propulsion", "orbital", "genome",
            # plasma / nuclear / energy
            "confinement", "magnetic field", "flux", "reactor", "fission",
            "fusion", "neutron", "proton", "ion", "quench", "helium",
            "tungsten", "radiation", "radioactive", "half-life", "nucleus",
            "accelerator", "collider", "detector",
            # materials / chemistry
            "lattice", "crystal", "alloy", "polymer", "substrate", "oxide",
            "conductivity", "resistivity", "annealing", "sputtering",
            "embrittlement", "diffusion", "solvent", "reagent", "titration",
            "enzyme", "protein", "catalyst", "compound", "molecule",
            # optics / waves / dynamics
            "laser", "optic", "refraction", "resonance", "oscillation",
            "damping", "viscosity", "turbulence", "momentum", "torque",
            "inertia", "harmonic", "spectrum", "attenuation",
            # space / earth
            "orbit", "satellite", "trajectory", "aerodynamic", "combustion",
            "turbine", "telescope", "galaxy", "nebula", "cosmic", "spacetime",
            "seismic", "atmospheric",
            # life sciences / computing
            "cellular", "mitochondri", "chromosome", "sequencing", "in vitro",
            "tensor", "convolution", "inference", "stochastic", "heuristic",
            "experimento", "hipotesis", "teoria", "medicion", "velocidad",
            "simulacion", "algoritmo", "frecuencia", "conductividad",
            "radiacion", "molecula", "energia"),
        1: ("science", "scientific", "physics", "chemistry", "biology",
            "astronomy", "engineering", "technology", "research", "laboratory",
            "observed", "derived", "computed", "phenomenon", "empirical",
            "apparatus", "instrument", "sample", "temperature", "pressure",
            "density", "energy", "particle", "wave", "field", "mass",
            "ciencia", "fisica", "quimica", "tecnologia", "investigacion",
            "laboratorio", "temperatura", "presion", "particula", "onda"),
    },
    "academic_paper": {
        3: ("et al", "doi", "arxiv", "peer-reviewed", "peer review",
            "supplementary material", "corresponding author", "isbn",
            "issn", "citation", "bibliography"),
        2: ("abstract", "keywords", "methodology", "related work",
            "prior work", "we propose", "we present", "our contribution",
            "future work", "acknowledgements", "limitations", "significance",
            "p-value", "confidence interval", "resumen", "palabras clave",
            "metodologia", "trabajo relacionado", "agradecimientos"),
        1: ("introduction", "conclusion", "discussion", "results", "method",
            "findings", "literature", "study", "cited", "appendix",
            "introduccion", "conclusion", "discusion", "resultados",
            "referencias", "apendice"),
    },
    "software_manual": {
        3: ("npm install", "pip install", "docker run", "git clone",
            "api endpoint", "return value", "stack trace", "changelog",
            "deprecated", "breaking change", "http status"),
        2: ("function", "parameter", "argument", "returns", "callback",
            "repository", "commit", "branch", "config", "cli", "sdk",
            "runtime", "compile", "dependency", "module", "namespace",
            "exception", "boolean", "json", "yaml", "regex", "localhost",
            "funcion", "parametro", "argumento", "dependencia", "modulo"),
        1: ("install", "usage", "example", "options", "default", "syntax",
            "output", "input", "version", "documentation", "reference",
            "instalar", "uso", "ejemplo", "opciones", "sintaxis"),
    },
    "engineering_spec": {
        3: ("tolerance", "part number", "torque", "datasheet", "rev.",
            "conformance", "shall comply", "acceptance criteria", "iso 9001",
            "bill of materials"),
        2: ("specification", "requirement", "dimension", "material",
            "assembly", "calibration", "throughput", "load", "stress",
            "actuator", "sensor", "voltage", "ampere", "millimetre",
            "millimeter", "schematic", "especificacion", "requisito",
            "tolerancia", "ensamble", "calibracion"),
        1: ("component", "system", "interface", "operation", "procedure",
            "standard", "verify", "install", "componente", "sistema",
            "procedimiento", "norma"),
    },
    "business_report": {
        3: ("quarterly results", "year over year", "kpi", "roadmap",
            "stakeholder", "executive summary", "action items",
            "resumen ejecutivo", "partes interesadas"),
        2: ("revenue", "growth", "strategy", "objective", "milestone",
            "deliverable", "headcount", "budget", "forecast", "market share",
            "initiative", "quarter", "performance", "risk", "mitigation",
            "ingresos", "crecimiento", "estrategia", "objetivo", "riesgo",
            "trimestre", "presupuesto"),
        1: ("team", "project", "progress", "plan", "review", "client",
            "customer", "meeting", "priority", "equipo", "proyecto",
            "avance", "cliente", "prioridad"),
    },
    "financial_ledger": {
        3: ("balance sheet", "cash flow", "accounts payable",
            "accounts receivable", "ebitda", "amortization", "amortisation",
            "gross margin", "net income", "vat", "invoice number",
            "estado de resultados", "flujo de efectivo", "cuentas por pagar"),
        2: ("revenue", "expense", "liability", "asset", "depreciation",
            "tax", "interest", "principal", "credit", "debit", "ledger",
            "fiscal", "audit", "reconciliation", "subtotal", "invoice",
            "ingreso", "egreso", "pasivo", "activo", "impuesto", "iva",
            "factura", "saldo"),
        1: ("total", "amount", "payment", "cost", "price", "currency",
            "usd", "eur", "mxn", "monto", "pago", "costo", "precio"),
    },
    "legal_instrument": {
        3: ("hereinafter", "whereas", "hereby", "notwithstanding",
            "in witness whereof", "governing law", "force majeure",
            "indemnify", "the parties agree", "por la presente",
            "las partes acuerdan", "en fe de lo cual", "clausula primera"),
        2: ("agreement", "contract", "clause", "provision", "obligation",
            "liability", "warranty", "termination", "jurisdiction",
            "confidential", "breach", "remedy", "arbitration", "party",
            "shall be", "contrato", "convenio", "clausula", "obligacion",
            "responsabilidad", "vigencia", "rescision", "jurisdiccion"),
        1: ("terms", "conditions", "rights", "license", "consent", "notice",
            "effective date", "signature", "terminos", "condiciones",
            "derechos", "licencia", "firma", "vigente"),
    },
    "medical_clinical": {
        3: ("mg/kg", "contraindication", "adverse event", "icd-10",
            "informed consent", "differential diagnosis", "prognosis",
            "posologia", "contraindicacion", "consentimiento informado"),
        2: ("patient", "diagnosis", "treatment", "symptom", "dosage",
            "dose", "clinical", "therapy", "prescription", "syndrome",
            "chronic", "acute", "physician", "pathology", "paciente",
            "diagnostico", "tratamiento", "sintoma", "dosis", "clinico",
            "terapia", "receta"),
        1: ("health", "medical", "care", "hospital", "nurse", "screening",
            "salud", "medico", "hospital", "enfermeria"),
    },
    "security_briefing": {
        3: ("cve-", "cvss", "privilege escalation", "lateral movement",
            "attack surface", "threat actor", "indicator of compromise",
            "proof of concept exploit", "remote code execution",
            "escalada de privilegios", "superficie de ataque"),
        2: ("vulnerability", "exploit", "payload", "reconnaissance",
            "penetration test", "mitigation", "hardening", "firewall",
            "malware", "phishing", "authentication", "encryption",
            "credential", "port scan", "subdomain", "vulnerabilidad",
            "cifrado", "autenticacion", "amenaza"),
        1: ("security", "risk", "threat", "attack", "breach", "audit",
            "scan", "target", "seguridad", "riesgo", "ataque", "auditoria"),
    },
    "data_analysis": {
        3: ("standard deviation", "confidence interval", "p-value",
            "regression", "correlation coefficient", "null hypothesis",
            "sample size", "desviacion estandar", "intervalo de confianza"),
        2: ("dataset", "distribution", "median", "variance", "outlier",
            "percentile", "histogram", "cohort", "baseline", "metric",
            "aggregate", "trend", "anomaly", "normalise", "normalize",
            "conjunto de datos", "mediana", "varianza", "percentil",
            "tendencia"),
        1: ("data", "analysis", "average", "mean", "total", "count",
            "chart", "graph", "table", "measure", "datos", "analisis",
            "promedio", "grafica"),
    },
    "editorial_feature": {
        3: ("by our correspondent", "op-ed", "in this essay",
            "the question is not", "reporting for"),
        2: ("argues", "arguably", "moreover", "perhaps", "consider",
            "narrative", "interview", "profile", "reflection", "essay",
            "critique", "commentary", "entrevista", "ensayo", "cronica",
            "reflexion", "opinion"),
        1: ("story", "reader", "writer", "society", "culture", "history",
            "century", "modern", "lector", "escritor", "sociedad",
            "cultura"),
    },
    "creative_literary": {
        3: ("chapter one", "once upon a time", "int.", "ext.", "fade in",
            "cut to:", "capitulo uno", "erase una vez"),
        2: ("whispered", "silence", "shadow", "dream", "heart", "memory",
            "beautiful", "stranger", "moonlight", "verse", "stanza",
            "protagonist", "susurro", "silencio", "sombra", "sueno",
            "corazon", "recuerdo", "verso"),
        1: ("she", "he", "they said", "looked", "walked", "felt", "smiled",
            "night", "morning", "noche", "manana", "miro", "sintio"),
    },
    "marketing_brochure": {
        3: ("limited time", "sign up now", "get started free", "book a demo",
            "money-back guarantee", "trusted by", "oferta limitada",
            "registrate ahora", "solicita una demo"),
        2: ("transform", "unlock", "boost", "seamless", "effortless",
            "revolutionary", "game-changing", "exclusive", "premium",
            "discover", "introducing", "why choose", "testimonial",
            "transforma", "descubre", "exclusivo", "revolucionario"),
        1: ("best", "fast", "easy", "new", "free", "save", "offer", "today",
            "customers", "mejor", "rapido", "facil", "nuevo", "gratis",
            "oferta", "hoy"),
    },
    "educational_course": {
        3: ("learning objectives", "by the end of this lesson",
            "exercise 1", "try it yourself", "check your understanding",
            "objetivos de aprendizaje", "al final de esta leccion",
            "ejercicio 1"),
        2: ("lesson", "module", "exercise", "quiz", "assignment", "student",
            "curriculum", "worksheet", "practice", "beginner", "step by step",
            "learn", "teaches", "leccion", "modulo", "ejercicio",
            "estudiante", "practica", "paso a paso", "aprender"),
        1: ("chapter", "example", "explain", "understand", "review",
            "summary", "capitulo", "ejemplo", "explicar", "resumen"),
    },
    "government_policy": {
        3: ("pursuant to article", "the ministry of", "official gazette",
            "public consultation", "diario oficial", "conforme al articulo",
            "secretaria de"),
        2: ("regulation", "directive", "ordinance", "authority", "citizen",
            "municipal", "federal", "statutory", "compliance", "mandate",
            "public sector", "reglamento", "ordenanza", "ciudadano",
            "municipal", "federal", "normativa"),
        1: ("government", "policy", "public", "department", "agency",
            "council", "gobierno", "politica", "publico", "dependencia"),
    },
    "historical_archive": {
        3: ("in the year of our lord", "the archive records",
            "born in", "died in", "archivo historico", "nacido en"),
        2: ("century", "dynasty", "empire", "revolution", "manuscript",
            "chronicle", "ancestor", "colonial", "medieval", "antiquity",
            "siglo", "dinastia", "imperio", "revolucion", "manuscrito",
            "colonial", "antepasado"),
        1: ("history", "historical", "ancient", "period", "era", "past",
            "recorded", "historia", "antiguo", "epoca", "pasado"),
    },
    "culinary_recipe": {
        3: ("preheat the oven", "until golden brown", "serves 4",
            "prep time", "cook time", "precalienta el horno",
            "tiempo de coccion", "rinde 4 porciones"),
        2: ("ingredients", "tablespoon", "teaspoon", "simmer", "saute",
            "whisk", "marinate", "garnish", "dough", "batter", "seasoning",
            "recipe", "ingredientes", "cucharada", "cucharadita", "sofreir",
            "marinar", "masa", "receta"),
        1: ("cup", "gram", "minutes", "bowl", "pan", "oven", "salt",
            "butter", "flour", "taza", "gramo", "minutos", "horno", "sal",
            "harina", "mantequilla"),
    },
    "personal_letter": {
        3: ("dear ", "yours sincerely", "yours faithfully", "with love",
            "querida", "querido", "atentamente", "un abrazo",
            "con carino"),
        2: ("i hope this finds you", "i wanted to tell you", "miss you",
            "thinking of you", "write back", "espero que estes bien",
            "te extrano", "pienso en ti"),
        1: ("hello", "hi", "regards", "best wishes", "take care",
            "hola", "saludos", "cuidate"),
    },
    "presentation_deck": {
        3: ("slide 1", "agenda", "key takeaways", "thank you / questions",
            "next steps", "diapositiva 1", "puntos clave"),
        2: ("overview", "highlights", "roadmap", "vision", "our approach",
            "the problem", "the solution", "q&a", "vision general",
            "el problema", "la solucion"),
        1: ("today", "welcome", "summary", "questions", "hoy",
            "bienvenidos", "preguntas"),
    },
}


# ─────────────────────────────────────────────────────────────────────────
#  STRUCTURAL DETECTORS — the strongest evidence family
# ─────────────────────────────────────────────────────────────────────────
_STRUCT = {
    "abstract_heading": (
        re.compile(r"^\s{0,3}(#{1,3}\s*)?(abstract|resumen|résumé)\s*$",
                   re.IGNORECASE | re.MULTILINE),
        {"academic_paper": 9.0}),
    "keywords_line": (
        re.compile(r"^\s*(#{1,4}\s*)?(keywords?|palabras\s+clave)\s*[::]",
                   re.IGNORECASE | re.MULTILINE),
        {"academic_paper": 6.0}),
    "references_heading": (
        re.compile(r"^\s{0,3}(#{1,3}\s*)?(references|bibliograf(y|ía|ia)|"
                   r"works\s+cited|referencias)\s*$",
                   re.IGNORECASE | re.MULTILINE),
        {"academic_paper": 7.0}),
    "imrad_run": (
        re.compile(r"(?is)(introduction|introducción).{0,6000}?"
                   r"(method|método|methodolog).{0,9000}?"
                   r"(result|resultado).{0,9000}?(discussion|discusión|"
                   r"conclusion|conclusión)"),
        {"academic_paper": 8.0}),
    "numeric_citation": (
        re.compile(r"\[\d{1,3}(?:\s*[,–-]\s*\d{1,3})*\]"),
        {"academic_paper": 3.0, "scientific_dark": 1.0}),
    "author_year_citation": (
        re.compile(r"\([A-ZÁÉÍÓÚÑ][A-Za-zÁÉÍÓÚÑáéíóúñ'’-]+"
                   r"(?:\s+(?:et\s+al\.?|and|&|y)\s+[A-Za-zÁÉÍÓÚÑ][\w'’-]+)?,\s*"
                   r"(?:19|20)\d{2}[a-z]?\)"),
        {"academic_paper": 4.0}),
    "doi_or_arxiv": (
        re.compile(r"(doi:\s*10\.\d{4,}|arxiv:\s*\d{4}\.\d{4,}|"
                   r"https?://doi\.org/)", re.IGNORECASE),
        {"academic_paper": 6.0}),
    "latex_math": (
        re.compile(r"(\$[^$\n]{2,}\$|\\begin\{(equation|align|matrix|"
                   r"theorem|proof)\}|\\frac\{|\\sum_|\\int_)"),
        {"academic_paper": 5.0, "scientific_dark": 4.0}),
    "unicode_math": (
        re.compile(r"[∑∫∂∇√≈≠≤≥±∞×÷µΩλθπσαβγΔ]"),
        {"scientific_dark": 2.5, "academic_paper": 1.5,
         "data_analysis": 1.5}),
    "si_units": (
        re.compile(r"\b\d+(?:[.,]\d+)?\s?(nm|µm|mm|cm|km|kg|mg|ms|µs|ns|"
                   r"GHz|MHz|kHz|Hz|kW|MW|mV|kV|°C|K|J|eV|mol|Pa|dB|"
                   r"Mbps|Gbps)\b"),
        {"scientific_dark": 3.0, "engineering_spec": 3.0}),
    "code_fence": (
        re.compile(r"^\s*```", re.MULTILINE),
        {"software_manual": 4.5, "scientific_dark": 1.0,
         "security_briefing": 1.5}),
    "shell_prompt": (
        re.compile(r"^\s*[$>#]\s+\w+", re.MULTILINE),
        {"software_manual": 3.0, "security_briefing": 2.0}),
    "code_identifier": (
        re.compile(r"\b\w+(?:_\w+){2,}\b|\b\w+(?:::|->)\w+"),
        {"software_manual": 2.0, "engineering_spec": 0.5}),
    "http_verb": (
        re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\s+/[\w/{}.-]*"),
        {"software_manual": 4.0}),
    "cve_id": (
        re.compile(r"\bCVE-\d{4}-\d{4,}\b", re.IGNORECASE),
        {"security_briefing": 7.0}),
    "ip_or_port": (
        re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?::\d{2,5})?\b"),
        {"security_briefing": 2.5, "software_manual": 1.0}),
    "legal_clause_numbering": (
        re.compile(r"^\s*\d{1,2}\.\d{1,2}(\.\d{1,2})?\s+[A-ZÁÉÍÓÚÑ]",
                   re.MULTILINE),
        {"legal_instrument": 4.0, "government_policy": 3.0,
         "engineering_spec": 2.0}),
    "defined_term": (
        re.compile(r'"[A-Z][^"]{2,30}"\s+(means|shall\s+mean)',
                   re.IGNORECASE),
        {"legal_instrument": 6.0}),
    "signature_block": (
        re.compile(r"^\s*_{6,}\s*$", re.MULTILINE),
        {"legal_instrument": 3.0, "personal_letter": 1.5}),
    "currency_amount": (
        re.compile(r"[$€£¥]\s?\d[\d,.]*|\b\d[\d,.]*\s?(USD|EUR|MXN|GBP)\b"),
        {"financial_ledger": 4.0, "business_report": 1.5}),
    "percentage": (
        re.compile(r"\b\d+(?:[.,]\d+)?\s?%"),
        {"financial_ledger": 1.5, "data_analysis": 1.5,
         "business_report": 1.0}),
    "fiscal_period": (
        re.compile(r"\b(Q[1-4]\s?(?:19|20)\d{2}|FY\s?(?:19|20)?\d{2}|"
                   r"[1-4]T\s?(?:19|20)\d{2})\b"),
        {"financial_ledger": 4.0, "business_report": 3.0}),
    "dosage": (
        re.compile(r"\b\d+(?:[.,]\d+)?\s?(mg|ml|mcg|µg|g|IU|UI)\b"
                   r"(?:\s?/\s?(kg|day|día|dose|dosis))?", re.IGNORECASE),
        {"medical_clinical": 5.0}),
    "ingredient_measure": (
        re.compile(r"^\s*[-*•]?\s*\d+(?:[.,/]\d+)?\s*(cups?|tbsp|tsp|"
                   r"tablespoons?|teaspoons?|grams?|g|kg|ml|oz|"
                   r"tazas?|cucharadas?|cucharaditas?|gramos?)\b",
                   re.IGNORECASE | re.MULTILINE),
        {"culinary_recipe": 6.0}),
    "salutation": (
        re.compile(r"^\s*(dear|querid[ao]|estimad[ao])\s+\w+",
                   re.IGNORECASE | re.MULTILINE),
        {"personal_letter": 6.0}),
    "verse_lines": (
        re.compile(r"(?:^.{1,45}$\n){5,}", re.MULTILINE),
        {"creative_literary": 3.0}),
    "dialogue": (
        re.compile(r'^\s*[—–]\s*[A-ZÁÉÍÓÚÑ]|^\s*"[A-Z][^"]{10,}[,.!?]"',
                   re.MULTILINE),
        {"creative_literary": 3.5}),
    "learning_objective": (
        re.compile(r"^\s*(#{1,4}\s*)?(learning\s+objectives?|"
                   r"objetivos?\s+de\s+aprendizaje|what\s+you.?ll\s+learn)",
                   re.IGNORECASE | re.MULTILINE),
        {"educational_course": 7.0}),
    "exercise_marker": (
        re.compile(r"^\s*(#{1,4}\s*)?(exercise|ejercicio|activity|"
                   r"actividad|quiz)\s*\d", re.IGNORECASE | re.MULTILINE),
        {"educational_course": 4.0}),
    "call_to_action": (
        re.compile(r"\b(sign\s+up|get\s+started|buy\s+now|learn\s+more|"
                   r"book\s+a\s+demo|contact\s+us|regístrate|"
                   r"compra\s+ahora|más\s+información)\b", re.IGNORECASE),
        {"marketing_brochure": 4.0}),
    "slide_marker": (
        re.compile(r"^\s*(slide|diapositiva)\s*\d+", re.IGNORECASE | re.MULTILINE),
        {"presentation_deck": 6.0}),
    "horizontal_rules": (
        re.compile(r"^\s*(-{3,}|\*{3,}|_{3,})\s*$", re.MULTILINE),
        {"presentation_deck": 1.5}),
}


# ─────────────────────────────────────────────────────────────────────────
#  Language detection — stopword frequency, five languages
# ─────────────────────────────────────────────────────────────────────────
_STOPWORDS = {
    "en": ("the", "and", "of", "to", "in", "is", "that", "for", "it", "with",
           "as", "this", "be", "are", "was", "on", "by", "an", "not", "which"),
    "es": ("de", "la", "que", "el", "en", "los", "del", "las", "por", "un",
           "para", "con", "una", "su", "al", "lo", "como", "más", "pero",
           "sus"),
    "pt": ("de", "que", "não", "uma", "para", "com", "por", "mais", "как",
           "dos", "das", "ele", "está", "são", "seu", "pelo", "isso", "ser"),
    "fr": ("le", "de", "un", "être", "et", "à", "il", "avoir", "ne", "je",
           "son", "que", "se", "qui", "dans", "pour", "pas", "sur", "les",
           "des"),
    "de": ("der", "die", "und", "in", "den", "von", "zu", "das", "mit",
           "sich", "des", "auf", "für", "ist", "im", "dem", "nicht", "ein",
           "eine", "als"),
}

_WORD_RE = re.compile(r"[a-záéíóúñüàèìòùâêîôûçãõäöß]+", re.IGNORECASE)


def detect_language(text: str) -> tuple:
    """(code, confidence) for the document's language.

    Stopword frequency, not a model: it is instant, dependency-free and
    accurate enough for the only decision it drives — which words PDFer
    itself writes into the page furniture (``page 3 of 9`` vs
    ``página 3 de 9``). It NEVER touches the user's content.
    """
    words = _WORD_RE.findall((text or "")[:60000].lower())
    if len(words) < 12:
        return ("en", 0.0)
    counts = {}
    for lang, stops in _STOPWORDS.items():
        stop_set = set(stops)
        counts[lang] = sum(1 for word in words if word in stop_set)
    total = sum(counts.values())
    if not total:
        return ("en", 0.0)
    best = max(counts, key=counts.get)
    ordered = sorted(counts.values(), reverse=True)
    margin = (ordered[0] - ordered[1]) / float(ordered[0]) if ordered[0] else 0.0
    return (best, round(min(1.0, margin * (counts[best] / float(len(words))) * 8), 3))


def normalise_nuance(value: str) -> str:
    """Map ANY user/LLM spelling of a nuance onto a catalog key.

    This is what makes the new ``nuance`` parameter forgiving: ``'science'``,
    ``'Scientific'``, ``'tech'``, ``'ciencia'`` and ``'scientific_dark'`` all
    arrive at the same theme. An unrecognised value returns ``''`` so the
    caller can fall back to detection rather than silently mis-styling.
    """
    text = re.sub(r"[\s_-]+", " ", str(value or "").strip().lower())
    if not text or text in ("auto", "detect", "automatic", "automatico"):
        return ""
    squashed = text.replace(" ", "_")
    if squashed in NUANCES:
        return squashed
    for key, spec in NUANCES.items():
        if text == key.replace("_", " "):
            return key
        for alias in spec["aliases"]:
            if text == alias or squashed == alias.replace(" ", "_"):
                return key
    # Loose containment last, longest alias first so "science" does not steal
    # a match that "data science" should have won.
    candidates = []
    for key, spec in NUANCES.items():
        for alias in spec["aliases"]:
            if alias in text or text in alias:
                candidates.append((len(alias), key))
    if candidates:
        return max(candidates)[1]
    return ""


class NuanceVerdict:
    """What the content is, how sure we are, and what evidence says so."""

    def __init__(self, nuance, confidence, scores, evidence, language,
                 language_confidence, metrics, source="detected",
                 runner_up="", runner_up_score=0.0):
        self.nuance = nuance
        self.confidence = round(float(confidence), 3)
        self.scores = scores or {}
        self.evidence = evidence or []
        self.language = language
        self.language_confidence = language_confidence
        self.metrics = metrics or {}
        self.source = source          # detected | explicit | llm | fallback
        self.runner_up = runner_up
        self.runner_up_score = round(float(runner_up_score), 3)

    # ── derived guidance for the theme layer ────────────────────────────
    @property
    def spec(self) -> dict:
        return NUANCES.get(self.nuance, NUANCES["minimal_note"])

    @property
    def label(self) -> str:
        return self.spec["label"]

    @property
    def decoration_budget(self) -> str:
        """How much ornament this content can SAFELY carry.

        The catalog ceiling, then lowered by two independent worries:

        * **Low confidence.** If PDFer is not sure what it is holding, it
          decorates less. Getting the ornament wrong on a document you have
          misread is how a composer looks foolish.
        * **Instruction density.** Content thick with dosages, tolerances,
          clause numbers or monetary amounts is content a reader must follow
          *exactly*. Ornament competes for attention there, and attention is
          the safety margin.
        """
        ceiling = self.spec.get("decoration", "restrained")
        level = DECORATION_LEVELS.index(ceiling)
        if self.confidence < 0.30:
            level = min(level, DECORATION_LEVELS.index("restrained"))
        elif self.confidence < 0.55:
            level = max(0, level - 1)
        if self.metrics.get("precision_critical"):
            level = min(level, DECORATION_LEVELS.index("restrained"))
        if self.nuance in ("legal_instrument", "medical_clinical",
                           "financial_ledger"):
            level = 0
        return DECORATION_LEVELS[max(0, level)]

    @property
    def prefers_dark(self) -> bool:
        return bool(self.spec.get("prefers", {}).get("dark", False))

    @property
    def pairing(self) -> str:
        return self.spec.get("prefers", {}).get("pairing", "neutral")

    @property
    def scale_ratio(self) -> float:
        return float(self.spec.get("prefers", {}).get("ratio", 1.25))

    def explain(self) -> str:
        """A paragraph a human can check the classifier's reasoning against.

        Printed into the agent log every run. A classifier whose reasoning is
        invisible cannot be argued with — and Angela is entitled to argue
        with it.
        """
        lines = ["Nuance: %s (%s) — confidence %.0f%%, source=%s"
                 % (self.nuance, self.label, self.confidence * 100, self.source)]
        if self.runner_up:
            lines.append("  runner-up: %s (%.2f vs %.2f)"
                         % (self.runner_up, self.runner_up_score,
                            self.scores.get(self.nuance, 0.0)))
        lines.append("  language: %s (%.0f%% sure) · decoration budget: %s"
                     % (self.language, self.language_confidence * 100,
                        self.decoration_budget))
        if self.evidence:
            lines.append("  evidence:")
            for item in self.evidence[:12]:
                lines.append("    • %s" % item)
        metrics = self.metrics
        lines.append("  shape: %d words, %d headings, %d tables, %d code "
                     "blocks, %d images, avg sentence %.1f words"
                     % (metrics.get("words", 0), metrics.get("headings", 0),
                        metrics.get("tables", 0), metrics.get("code_blocks", 0),
                        metrics.get("images", 0),
                        metrics.get("avg_sentence_words", 0.0)))
        return "\n".join(lines)

    def as_dict(self) -> dict:
        return {
            "nuance": self.nuance, "label": self.label,
            "confidence": self.confidence, "source": self.source,
            "runner_up": self.runner_up, "runner_up_score": self.runner_up_score,
            "language": self.language,
            "language_confidence": self.language_confidence,
            "decoration_budget": self.decoration_budget,
            "prefers_dark": self.prefers_dark, "pairing": self.pairing,
            "scale_ratio": self.scale_ratio,
            "evidence": list(self.evidence[:20]),
            "metrics": dict(self.metrics),
            "top_scores": dict(sorted(self.scores.items(),
                                      key=lambda kv: kv[1], reverse=True)[:6]),
        }

    def __repr__(self) -> str:
        return "NuanceVerdict(%s, %.2f, %s)" % (self.nuance, self.confidence,
                                                self.source)


def _measure_shape(text: str) -> dict:
    """Structural metrics — the document's silhouette, independent of topic."""
    lines = text.split("\n")
    words = _WORD_RE.findall(text)
    sentences = [s for s in re.split(r"[.!?¿¡]+\s", text) if s.strip()]
    sentence_lengths = [len(_WORD_RE.findall(s)) for s in sentences[:400]]
    headings = len(re.findall(r"^\s{0,3}#{1,6}\s+\S", text, re.MULTILINE))
    headings += len(re.findall(r"^\s*<h[1-6][ >]", text,
                               re.MULTILINE | re.IGNORECASE))
    table_rows = len(re.findall(r"^\s*\|.*\|\s*$", text, re.MULTILINE))
    html_tables = len(re.findall(r"<table[ >]", text, re.IGNORECASE))
    code_blocks = len(re.findall(r"^\s*```", text, re.MULTILINE)) // 2
    code_blocks += len(re.findall(r"<pre[ >]", text, re.IGNORECASE))
    images = len(re.findall(r"!\[[^\]]*\]\([^)]+\)", text))
    images += len(re.findall(r"<img[ >]", text, re.IGNORECASE))
    bullets = len(re.findall(r"^\s*[-*•+]\s+\S", text, re.MULTILINE))
    numbered = len(re.findall(r"^\s*\d+[.)]\s+\S", text, re.MULTILINE))
    exclamations = text.count("!")
    questions = text.count("?")

    word_count = len(words)
    avg_sentence = (sum(sentence_lengths) / float(len(sentence_lengths))
                    if sentence_lengths else 0.0)
    # Content the reader must follow EXACTLY — the decoration brake.
    precision_hits = (
        len(_STRUCT["dosage"][0].findall(text))
        + len(_STRUCT["si_units"][0].findall(text))
        + len(_STRUCT["currency_amount"][0].findall(text))
        + len(_STRUCT["legal_clause_numbering"][0].findall(text)))

    return {
        "chars": len(text),
        "words": word_count,
        "lines": len(lines),
        "headings": headings,
        "tables": max(table_rows // 3, html_tables),
        "table_rows": table_rows,
        "code_blocks": code_blocks,
        "images": images,
        "bullets": bullets,
        "numbered_items": numbered,
        "exclamations": exclamations,
        "questions": questions,
        "avg_sentence_words": round(avg_sentence, 2),
        "long_sentences": sum(1 for n in sentence_lengths if n > 28),
        "short_lines": sum(1 for line in lines if 0 < len(line.strip()) < 46),
        "precision_hits": precision_hits,
        "precision_critical": precision_hits >= 8,
        "density_code": round(code_blocks / max(1.0, word_count / 500.0), 3),
        "density_table": round(table_rows / max(1.0, word_count / 500.0), 3),
    }


def _register_bias(metrics: dict, text: str) -> dict:
    """Voice-based nudges — the tie-breaker family.

    Small on purpose (±2 points against lexicon scores in the tens). Register
    should decide a photo-finish between *manual* and *brochure*; it should
    never overturn an abstract-plus-references verdict.
    """
    bias = {}
    words = max(1, metrics["words"])
    per_1000 = 1000.0 / words

    if metrics["avg_sentence_words"] > 26:
        bias["legal_instrument"] = bias.get("legal_instrument", 0) + 1.6
        bias["academic_paper"] = bias.get("academic_paper", 0) + 1.2
        bias["government_policy"] = bias.get("government_policy", 0) + 1.0
    elif 0 < metrics["avg_sentence_words"] < 12:
        bias["marketing_brochure"] = bias.get("marketing_brochure", 0) + 1.4
        bias["presentation_deck"] = bias.get("presentation_deck", 0) + 1.6

    if metrics["exclamations"] * per_1000 > 3:
        bias["marketing_brochure"] = bias.get("marketing_brochure", 0) + 2.0
        bias["academic_paper"] = bias.get("academic_paper", 0) - 2.0
        bias["legal_instrument"] = bias.get("legal_instrument", 0) - 2.0

    second_person = len(re.findall(r"\b(you|your|tú|usted|tu)\b", text,
                                   re.IGNORECASE))
    if second_person * per_1000 > 10:
        bias["marketing_brochure"] = bias.get("marketing_brochure", 0) + 1.5
        bias["educational_course"] = bias.get("educational_course", 0) + 1.5
        bias["software_manual"] = bias.get("software_manual", 0) + 1.0
        bias["academic_paper"] = bias.get("academic_paper", 0) - 1.5

    first_person = len(re.findall(r"\b(i|me|my|yo|mi)\b", text, re.IGNORECASE))
    if first_person * per_1000 > 8:
        bias["personal_letter"] = bias.get("personal_letter", 0) + 2.0
        bias["creative_literary"] = bias.get("creative_literary", 0) + 1.2
        bias["legal_instrument"] = bias.get("legal_instrument", 0) - 1.5

    passive = len(re.findall(r"\b(was|were|is|are|been|be)\s+\w+(ed|en)\b",
                             text, re.IGNORECASE))
    if passive * per_1000 > 12:
        bias["academic_paper"] = bias.get("academic_paper", 0) + 1.6
        bias["engineering_spec"] = bias.get("engineering_spec", 0) + 1.0

    if metrics["density_code"] > 1.5:
        bias["software_manual"] = bias.get("software_manual", 0) + 2.5
    if metrics["density_table"] > 6:
        bias["financial_ledger"] = bias.get("financial_ledger", 0) + 1.5
        bias["data_analysis"] = bias.get("data_analysis", 0) + 1.5
    if metrics["short_lines"] > 25 and metrics["avg_sentence_words"] < 14:
        bias["creative_literary"] = bias.get("creative_literary", 0) + 1.5
    return bias


def classify(text: str, hint: str = "", images: int = 0,
             title: str = "") -> "NuanceVerdict":
    """Classify *text*. NEVER raises — an unreadable document is a verdict too.

    *hint* is the new ``nuance`` config parameter. When it resolves to a
    catalog entry it WINS outright (``source='explicit'``): the user asked for
    a look, and detection does not get a vote. Detection still runs so the
    evidence is available in the log — an explicit choice that disagrees with
    the content is worth being able to see.
    """
    try:
        return _classify_inner(text or "", hint, images, title)
    except Exception as exc:
        return NuanceVerdict(
            "minimal_note", 0.0, {},
            ["classifier failed (%s: %s) — fell back to the plain treatment, "
             "which is always safe" % (type(exc).__name__, exc)],
            "en", 0.0, {"words": 0}, source="fallback")


def _classify_inner(text, hint, images, title):
    forced = normalise_nuance(hint)
    # Cap the analysed window: classification is about *character*, and the
    # first 240 kB carries it. A 40 MB dump must not stall a render.
    sample = text[:240000]
    haystack = (title + "\n" + sample).lower()
    metrics = _measure_shape(sample)
    metrics["images"] = max(metrics.get("images", 0), int(images or 0))
    language, language_confidence = detect_language(sample)

    scores = {key: 0.0 for key in NUANCES}
    evidence = []

    # ── 1. LEXICON, log-damped so breadth beats repetition ──────────────
    for nuance, tiers in _LEXICON.items():
        matched_terms = 0
        for weight, terms in tiers.items():
            for term in terms:
                if " " in term or "-" in term:
                    count = haystack.count(term)
                else:
                    count = len(re.findall(r"\b%s\w{0,3}\b" % re.escape(term),
                                           haystack))
                if count:
                    scores[nuance] += weight * (1.0 + math.log(count))
                    matched_terms += 1
        if matched_terms >= 3:
            evidence.append("%s: %d distinct terms matched (score %.1f)"
                            % (nuance, matched_terms, scores[nuance]))

    # Normalise for length — a 50-page document must not out-score a
    # one-pager purely by having more words in it.
    length_factor = 1.0 / max(1.0, math.log10(max(10, metrics["words"])) - 0.7)
    for nuance in scores:
        scores[nuance] *= length_factor

    # Snapshot the vocabulary verdict BEFORE structure votes. This is what
    # corroboration is measured against below.
    lexical_support = dict(scores)

    # ── 2. STRUCTURE, weighted ~3x — the decisive family ────────────────
    #
    # ⚠️ CORROBORATION RULE (added after a measured miss, 2026-09-06).
    # Many structural signals are AMBIGUOUS between domains by nature.
    # ``si_units`` fires on "5 T", "150 MHz", "2 MW/m2" and awards
    # ``scientific_dark`` and ``engineering_spec`` equally — because
    # measurements alone genuinely cannot tell you whether you are reading an
    # explanation of plasma confinement or a bill of materials.
    #
    # Without this rule a tokamak article scored engineering_spec 9.4 vs
    # scientific_dark 7.2 and was dressed as a parts list, DESPITE having
    # zero engineering-spec vocabulary — no "tolerance", no "requirement", no
    # part number. Structure had answered "measurements are present"; nothing
    # had answered "of what discipline".
    #
    # So a structural award is DAMPED when its domain has no lexical support:
    # structure establishes the SHAPE, vocabulary establishes the FIELD, and a
    # shape with no matching field is weak evidence. Unambiguous signals
    # (``abstract_heading``, ``cve_id``, ``salutation``) are exempt — they name
    # their domain outright, and a paper whose abstract is its only English
    # sentence is still a paper.
    total_lexical = sum(lexical_support.values()) or 1.0
    unambiguous = {name for name, (_p, awards) in _STRUCT.items()
                   if len(awards) == 1}

    for name, (pattern, awards) in _STRUCT.items():
        try:
            hits = len(pattern.findall(sample))
        except Exception:
            continue
        if not hits:
            continue
        strength = 1.0 + math.log(hits) if hits > 1 else 1.0
        applied = {}
        for nuance, weight in awards.items():
            corroboration = 1.0
            if name not in unambiguous:
                share = lexical_support.get(nuance, 0.0) / total_lexical
                if share < 0.02:
                    # The vocabulary of this domain is essentially absent.
                    corroboration = 0.40
                elif share < 0.06:
                    corroboration = 0.70
            award = weight * strength * corroboration
            scores[nuance] = scores.get(nuance, 0.0) + award
            applied[nuance] = (award, corroboration)
        evidence.append("structure '%s' ×%d → %s"
                        % (name, hits,
                           ", ".join(
                               "%s+%.1f%s" % (n, a,
                                              "" if c >= 0.99
                                              else " (uncorroborated ×%.2f)" % c)
                               for n, (a, c) in applied.items())))

    # ── 3. REGISTER, the tie-breaker ────────────────────────────────────
    for nuance, delta in _register_bias(metrics, sample).items():
        scores[nuance] = scores.get(nuance, 0.0) + delta
        if abs(delta) >= 1.5:
            evidence.append("register → %s %+.1f" % (nuance, delta))

    # A document that is mostly images is a portfolio, not an essay.
    if metrics["images"] >= 3 and metrics["words"] < 400:
        scores["presentation_deck"] += 4.0
        scores["marketing_brochure"] += 2.0
        evidence.append("image-dominant with little prose → deck/brochure")

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best, best_score = ranked[0]
    runner_up, runner_score = (ranked[1] if len(ranked) > 1 else ("", 0.0))

    # Confidence combines ABSOLUTE evidence (is there enough to judge at all?)
    # with the MARGIN over the runner-up (is the judgement clear?). Both must
    # be healthy: a document scoring 40 vs 39 is a coin-flip, and one scoring
    # 3 vs 0 is a rounding error.
    if best_score <= 0.5:
        nuance, confidence = "minimal_note", 0.0
        evidence.append("no domain evidence above the noise floor → plain "
                        "treatment")
    else:
        margin = ((best_score - runner_score) / best_score
                  if best_score > 0 else 0.0)
        absolute = min(1.0, best_score / 22.0)
        confidence = max(0.0, min(1.0, 0.45 * absolute + 0.55 * margin))
        nuance = best

    if metrics["words"] < 40 and not forced:
        nuance = "minimal_note" if confidence < 0.6 else nuance
        confidence = min(confidence, 0.35)
        evidence.append("very short document — confidence capped")

    # ── NOISE GUARD ─────────────────────────────────────────────────────
    # Content that is mostly NOT letters (mojibake, a stray binary, a base64
    # blob that slipped past the loader) can still trip a few lexical
    # patterns by chance. It must never come back CONFIDENT: a confidently
    # wrong classifier hands a random byte-dump the full dark-science
    # treatment, which looks like a deliberate choice rather than the
    # accident it is. Low confidence is what pulls the decoration budget
    # down to 'restrained', so the wrong guess stays quiet.
    letters = sum(1 for ch in sample[:20000] if ch.isalpha() or ch.isspace())
    letter_ratio = letters / float(min(len(sample), 20000) or 1)
    if sample and letter_ratio < 0.72:
        confidence = min(confidence, 0.25)
        evidence.append(
            "only %.0f%% of the sample is letters or spaces — this may not be "
            "prose at all, so confidence is capped and ornament held back"
            % (letter_ratio * 100))

    if forced:
        evidence.insert(0, "EXPLICIT nuance=%r supplied — it wins over "
                           "detection (which said %s @ %.0f%%)"
                        % (hint, nuance, confidence * 100))
        return NuanceVerdict(forced, 1.0, scores, evidence, language,
                             language_confidence, metrics, source="explicit",
                             runner_up=nuance, runner_up_score=best_score)

    return NuanceVerdict(nuance, confidence, scores, evidence, language,
                         language_confidence, metrics, source="detected",
                         runner_up=runner_up, runner_up_score=runner_score)

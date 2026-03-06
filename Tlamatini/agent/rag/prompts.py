from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Contextualization prompt for history-aware question rewriting
CONTEXTUALIZE_Q_SYSTEM_PROMPT = (
    "You are a conversation context specialist. Given chat history and a user's latest question, "
    "reformulate the question into a clear, self-contained query that preserves the original intent "
    "while being fully understandable without the conversation context.\n\n"
    "CRITICAL RULES:\n"
    "a. DO NOT answer the question - only reformulate it\n"
    "b. Preserve all technical terms, specific entities, and domain context from the original question\n"
    "c. If the question references 'this', 'that', 'it', etc., replace with specific nouns from chat history\n"
    "d. Maintain the same question type (yes/no, how-to, what-is, etc.)\n"
    "e. Keep the reformulated question concise but complete\n\n"
    "f. Return ONLY the reformulated question, nothing else."
)

def get_contextualize_q_prompt() -> ChatPromptTemplate:
    return ChatPromptTemplate.from_messages(
        [
            ("system", CONTEXTUALIZE_Q_SYSTEM_PROMPT),
            MessagesPlaceholder("chat_history"),
            ("human", "{input}"),
        ]
    )

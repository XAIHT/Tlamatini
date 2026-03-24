// ============================================================
// agent_page_ui.js  –  UI state helpers (enable/disable, busy, spinner)
// ============================================================

function setContextText(txt) {
    const full = txt || "";

    if (contextDataSpan) {
        contextDataSpan.textContent = full;
        contextDataSpan.title = full;
    }
    if (contextMobile) {
        contextMobile.title = full;
        if (window.bootstrap) {
            const tip = bootstrap.Tooltip.getInstance(contextMobile);
            if (tip) tip.dispose();
            new bootstrap.Tooltip(contextMobile);
        }
    }
}

function updateViewContextDirMenuState() {
    if (viewContextDirInCanvasMenu) {
        if (actualContextDir !== null && actualContextDir !== '') {
            viewContextDirInCanvasMenu.parentElement.style.display = 'block';
        } else {
            viewContextDirInCanvasMenu.parentElement.style.display = 'none';
        }
    }
    updateOpenInMenuState();
}

// --- SVG icon data for "Open in..." menu items ---
const openInAppIcons = {
    explorer: '<svg viewBox="0 0 16 16" class="open-in-app-icon" fill="#FFD75E"><path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h3.879a1.5 1.5 0 0 1 1.06.44l.44.439a.5.5 0 0 0 .354.146H13.5A1.5 1.5 0 0 1 15 4.5v1H1V3.5zM1 6h14v7.5a1.5 1.5 0 0 1-1.5 1.5h-11A1.5 1.5 0 0 1 1 13.5V6z"/></svg>',
    vscode: '<svg viewBox="0 0 100 100" class="open-in-app-icon"><path d="M74.9 97.3l20.1-9.7V12.4L74.9 2.7 34.8 38.8 14.3 23.5 5 27v46l9.3 3.5 20.5-15.3 40.1 36.1zm-4.7-73.9L45.6 44.2l24.6 20.8V23.4zM24.3 50l-8.4 6.3V43.7L24.3 50z" fill="#007ACC"/></svg>',
    antigravity: '<svg viewBox="0 0 16 16" class="open-in-app-icon"><circle cx="8" cy="8" r="7" fill="none" stroke="#A78BFA" stroke-width="1.2"/><path d="M8 2C5 5 4 8 5 11c1 3 5 3 6 0 1-3 0-6-3-9z" fill="#A78BFA" opacity="0.85"/><circle cx="8" cy="7" r="1.5" fill="#E0D4FC"/></svg>'
};

/**
 * Update the "Open in..." dropdown visibility and enabled state.
 * Shown only when installedApps has items; enabled only when actualContextDir is set.
 */
function updateOpenInMenuState() {
    if (!openInDropdownItem || !openInMenuButton) return;

    if (installedApps.length === 0) {
        openInDropdownItem.style.display = 'none';
        return;
    }

    openInDropdownItem.style.display = '';

    if (actualContextDir !== null && actualContextDir !== '') {
        openInMenuButton.classList.remove('disabled-link');
        openInMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    } else {
        openInMenuButton.classList.add('disabled-link');
        openInMenuButton.removeAttribute('data-bs-toggle');
    }
}

/**
 * Fetch installed apps from the server and populate the "Open in..." dropdown.
 */
function detectInstalledApps() {
    fetch('/agent/detect_installed_apps/')
        .then(response => response.json())
        .then(data => {
            if (data.success && Array.isArray(data.apps)) {
                installedApps = data.apps.filter(app => app.available);
                renderOpenInMenu();
                updateOpenInMenuState();
            }
        })
        .catch(err => {
            console.error('Failed to detect installed apps:', err);
        });
}

/**
 * Render the "Open in..." dropdown menu items based on detected apps.
 */
function renderOpenInMenu() {
    if (!openInMenuList) return;
    openInMenuList.innerHTML = '';

    installedApps.forEach(app => {
        const li = document.createElement('li');
        const a = document.createElement('a');
        a.className = 'dropdown-item menu-entry open-in-menu-item';
        a.href = '#';

        const iconHtml = openInAppIcons[app.id] || '';
        a.innerHTML = iconHtml + '<span>' + app.name + '</span>';

        a.addEventListener('click', (e) => {
            e.preventDefault();
            if (!actualContextDir) return;
            openDirectoryInApp(app.id);
        });

        li.appendChild(a);
        openInMenuList.appendChild(li);
    });
}

/**
 * Send POST request to open the context directory in the given app.
 */
function openDirectoryInApp(appId) {
    const formData = new FormData();
    formData.append('csrfmiddlewaretoken', getCsrfToken());
    formData.append('app_id', appId);
    formData.append('directory', actualContextDir);

    fetch('/agent/open_in_app/', {
        method: 'POST',
        body: formData
    })
        .then(response => response.json())
        .then(data => {
            if (data.error) {
                console.error('Error opening in app:', data.error);
            } else {
                console.log('--- Opened directory in ' + appId);
            }
        })
        .catch(err => {
            console.error('Failed to open in app:', err);
        });
}

function setTitleBusy(isBusy) {
    titleBusyPrefix = isBusy ? "⏳ " : "";
}

function isBusyMessageRequest(message) {
    if (!message) return false;
    const m = String(message);
    return (
        m.includes("Your request is being processed by the LLM.")
    );
}

function isBusyMessageContext(message) {
    if (!message) return false;
    const m = String(message);
    return (
        m.includes("Your agent is loading the context.")
    );
}

function debounce(func, wait = 250) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => { func.apply(this, args); }, wait);
    };
}

function genericTokenCounting(text) {
    return text.length / 4;
}

function updateLineNumbers() {
    const lines = textEditorCode.textContent.split('\n');
    lineNumbers.value = lines.map((_, i) => i + 1).join('\n');
}

/**
 * Disable all interactive controls during a long operation.
 */
function disableControlsDuringOperation() {
    chatInput.readOnly = true;
    chatInput.style.backgroundColor = 'gray';
    if (!document.getElementById(spinnerId)) {
        const waitWidget = document.createElement('img');
        waitWidget.id = spinnerId;
        waitWidget.src = '/static/agent/img/spinner.svg';
        waitWidget.style.width = '100px';
        waitWidget.style.height = '100px';
        waitWidget.style.position = 'absolute';
        waitWidget.style.top = '50%';
        waitWidget.style.left = '50%';
        waitWidget.style.transform = 'translate(-50%, -50%)';
        waitWidget.style.zIndex = '1000';
        chatLog.appendChild(waitWidget);
    }
    contextButton.disabled = true;
    openEnabled = false;
    contextEnabled = false;
    cleanCanvasEnabled = false;
    reConnectEnabled = false;
    reConnectButton.disabled = true;
    cleanHistoryButton.disabled = true;
    cleanHistoryButton.style.backgroundColor = "#808080";
    cleanHistoryEnabled = false;
    contextMenuButton.setAttribute('disabled', 'disabled');
    contextMenuButton.removeAttribute('data-bs-toggle');
    mcpsMenuButton.setAttribute('disabled', 'disabled');
    mcpsMenuButton.removeAttribute('data-bs-toggle');
    if (openInMenuButton) {
        openInMenuButton.classList.add('disabled-link');
        openInMenuButton.removeAttribute('data-bs-toggle');
    }
    // Keep agentsMenuButton enabled so "Agentic Control Panel" remains accessible
    // Only disable the "Configure Agents" entry
    const configureAgentsItem = document.getElementById('enable-agents');
    if (configureAgentsItem) {
        configureAgentsItem.classList.add('disabled');
        configureAgentsItem.style.pointerEvents = 'none';
        configureAgentsItem.style.opacity = '0.5';
    }
    chatSubmitButton.textContent = 'Cancel';
    cleanCanvasButton.style.backgroundColor = "#808080";
    cleanCanvasButton.disabled = true;
    reopenOpenCanvasButton.style.backgroundColor = "#808080";
    reopenOpenCanvasButton.disabled = true;
    copyCanvasButton.style.backgroundColor = "#808080";
    copyCanvasButton.disabled = true;
    contextButton.style.backgroundColor = "#808080";
    contextButton.disabled = true;
    inLongOperation = true;
}

/**
 * Re-enable all controls after an operation completes.
 */
function enableControlsAfterOperation() {
    setTitleBusy(false);
    contextEnabled = true;
    contextButton.style.backgroundColor = "darkgreen";
    contextButton.disabled = false;
    contextButtonClicked = false;
    contextButton.textContent = "Use as context";
    chatInput.readOnly = false;
    chatInput.style.backgroundColor = '#40414F';
    const existingSpinner = document.getElementById(spinnerId);
    if (existingSpinner && existingSpinner.parentNode) {
        existingSpinner.parentNode.removeChild(existingSpinner);
    }

    if (canvasSettedAsContext) {
        contextButton.textContent = "Used as context";
        contextButton.style.backgroundColor = "#808080";
    } else {
        if (canvasLoaded) {
            contextButton.textContent = "Use as context";
            contextButton.style.backgroundColor = "darkgreen";
        } else {
            contextButton.textContent = "Use as context";
            contextButton.style.backgroundColor = "#808080";
        }
    }

    openEnabled = true;
    reConnectEnabled = true;
    contextEnabled = true;
    cleanCanvasEnabled = true;
    reConnectButton.disabled = false;
    cleanHistoryButton.disabled = false;
    cleanHistoryButton.style.backgroundColor = "darkgreen";
    cleanHistoryEnabled = true;
    contextMenuButton.removeAttribute('disabled', 'disabled');
    contextMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    mcpsMenuButton.removeAttribute('disabled', 'disabled');
    mcpsMenuButton.setAttribute('data-bs-toggle', 'dropdown');
    updateOpenInMenuState();
    // Re-enable the "Configure Agents" entry
    const configureAgentsItem = document.getElementById('enable-agents');
    if (configureAgentsItem) {
        configureAgentsItem.classList.remove('disabled');
        configureAgentsItem.style.pointerEvents = '';
        configureAgentsItem.style.opacity = '';
    }

    if (canvasLoaded === true) {
        cleanCanvasButton.style.backgroundColor = "darkgreen";
        cleanCanvasButton.disabled = false;
        reopenOpenCanvasButton.style.backgroundColor = "darkgreen";
        reopenOpenCanvasButton.disabled = false;
        copyCanvasButton.style.backgroundColor = "darkgreen";
        copyCanvasButton.disabled = false;
        contextButton.disabled = false;
    } else {
        cleanCanvasButton.style.backgroundColor = "#808080";
        cleanCanvasButton.disabled = true;
        reopenOpenCanvasButton.style.backgroundColor = "#808080";
        reopenOpenCanvasButton.disabled = true;
        copyCanvasButton.style.backgroundColor = "#808080";
        copyCanvasButton.disabled = true;
        contextButton.disabled = true;
    }

    chatSubmitButton.textContent = 'Send';
    inLongOperation = false;
    lapseLoadingContext = false;
}

/**
 * Enable canvas-related buttons (after canvas load).
 */
function enableCanvasButtons() {
    cleanCanvasButton.style.backgroundColor = "darkgreen";
    cleanCanvasButton.disabled = false;
    reopenOpenCanvasButton.style.backgroundColor = "darkgreen";
    reopenOpenCanvasButton.disabled = false;
    copyCanvasButton.style.backgroundColor = "darkgreen";
    copyCanvasButton.disabled = false;
    contextButton.style.backgroundColor = "darkgreen";
    contextButton.disabled = false;
}

/**
 * Disable canvas-related buttons (after canvas clean).
 */
function disableCanvasButtons() {
    cleanCanvasButton.style.backgroundColor = "#808080";
    cleanCanvasButton.disabled = true;
    reopenOpenCanvasButton.style.backgroundColor = "#808080";
    reopenOpenCanvasButton.disabled = true;
    copyCanvasButton.style.backgroundColor = "#808080";
    copyCanvasButton.disabled = true;
    contextButton.style.backgroundColor = "#808080";
    contextButton.disabled = true;
}

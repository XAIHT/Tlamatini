import js from "@eslint/js";
import globals from "globals";

export default [
    // Ignore backup files
    {
        ignores: ["**/*.bak"],
    },

    // Base: ESLint recommended rules
    js.configs.recommended,

    {
        // Only lint our JS source files
        files: ["Tlamatini/agent/static/agent/js/**/*.js"],

        languageOptions: {
            ecmaVersion: 2021,
            sourceType: "script", // Browser scripts loaded via <script> tags
            globals: {
                ...globals.browser,

                // jQuery
                $: "readonly",
                jQuery: "readonly",

                // Libraries loaded globally
                bootstrap: "readonly",
                marked: "readonly",
                hljs: "readonly",
                DOMPurify: "readonly",
                Sortable: "readonly",

                // Cross-file globals: agent_page_state.js
                sendChatSocketMessage: "readonly",
                isChatSocketOpen: "readonly",
                restoreConnectedSocketUi: "readonly",
                applyDisconnectedSocketUi: "readonly",
                userUsername: "readonly",
                chatLog: "readonly",
                chatSocket: "readonly",
                contextButtonClicked: "writable",
                canvasSettedAsContext: "writable",
                confirmationByUser: "writable",
                inLongOperation: "writable",
                canvasLoaded: "writable",
                openEnabled: "writable",
                reConnectEnabled: "writable",
                contextEnabled: "writable",
                cleanCanvasEnabled: "writable",
                actualContextDir: "writable",
                lapseLoadingContext: "writable",
                clearContextEnabled: "writable",
                cleanHistoryEnabled: "writable",
                fileTypeOmissions: "writable",
                textEditorCode: "writable",
                chatHistory: "writable",
                historyIndex: "writable",
                tempInput: "writable",
                buildingInitial: "writable",
                loadCatalogOfPrompts: "readonly",
                spinnerId: "readonly",
                maximalTheoricTokens: "readonly",
                MAX_MCPS: "readonly",
                MAX_TOOLS: "readonly",
                MAX_AGENTS: "readonly",
                textEditorPre: "readonly",
                lineNumbers: "readonly",
                openButton: "readonly",
                saveAsButton: "readonly",
                contextButton: "readonly",
                cleanCanvasButton: "readonly",
                chatInput: "readonly",
                chatSubmitButton: "readonly",
                logoutButton: "readonly",
                reopenOpenCanvasButton: "readonly",
                copyCanvasButton: "readonly",
                confirmationDialogMessage: "readonly",
                confirmationPrimaryDialogLegend: "readonly",
                confirmationSecondaryDialogLegend: "readonly",
                reConnectButton: "readonly",
                cleanHistoryButton: "readonly",
                contextMenuButton: "readonly",
                mcpsMenuButton: "readonly",
                agentsMenuButton: "readonly",
                filenameDivRight: "readonly",
                filenameDivLeft: "readonly",
                setDirContextMenu: "readonly",
                setFileContextMenu: "readonly",
                viewContextDirInCanvasMenu: "readonly",
                contextInfoDiv: "readonly",
                contextDataSpan: "readonly",
                contextMobile: "readonly",
                clearContextButton: "readonly",
                omissionsDialogMessage: "readonly",
                omissionsPrimaryDialogLegend: "readonly",
                omissionsSecondaryDialogLegend: "readonly",
                omissionContentInput: "readonly",
                mcpsDialogMessage: "readonly",
                mcpsPrimaryDialogLegend: "readonly",
                mcpsSecondaryDialogLegend: "readonly",
                mcpsThirdtiaryDialogLegend: "readonly",
                agentsDialogMessage: "readonly",
                agentsPrimaryDialogLegend: "readonly",
                agentsSecondaryDialogLegend: "readonly",
                mcp1: "readonly",
                mcp2: "readonly",
                label_mcp1: "readonly",
                label_mcp2: "readonly",
                toolMcpsList: "readonly",
                agentsList: "readonly",
                mcp1_enabled: "writable",
                mcp2_enabled: "writable",
                tools: "writable",
                agents: "writable",

                // Cross-file globals: agent_page_state.js (Open In)
                openInDropdownItem: "readonly",
                openInMenuButton: "readonly",
                openInMenuList: "readonly",
                installedApps: "writable",
                getCsrfToken: "readonly",

                // Cross-file globals: agent_page_ui.js
                setContextText: "readonly",
                updateViewContextDirMenuState: "readonly",
                detectInstalledApps: "readonly",
                setTitleBusy: "readonly",
                isBusyMessageRequest: "readonly",
                isBusyMessageContext: "readonly",
                debounce: "readonly",
                genericTokenCounting: "readonly",
                updateLineNumbers: "readonly",
                disableControlsDuringOperation: "readonly",
                enableControlsAfterOperation: "readonly",
                enableCanvasButtons: "readonly",
                disableCanvasButtons: "readonly",

                // Cross-file globals: agent_page_canvas.js
                getLanguageClass: "readonly",
                extractExtension: "readonly",
                replaceCodeElement: "readonly",
                loadCanvas: "readonly",
                loadCanvasFromFileInContentGenerated: "readonly",
                loadCanvasWithThisContent: "readonly",
                openCanvas: "readonly",
                reopenCanvas: "readonly",
                cleanCanvas: "readonly",
                copyCanvasToClipboard: "readonly",
                loadFileContent: "readonly",

                // Cross-file globals: agent_page_dialogs.js
                DIALOG_BUTTON_CSS: "readonly",
                styleDialogButtons: "readonly",
                makeDialogButtons: "readonly",
                preRenderConfirmationDialog: "readonly",
                renderConfirmationDialog: "readonly",
                preRenderOmissionsDialog: "readonly",
                renderOmissionsDialog: "readonly",
                preRenderMcpsDialog: "readonly",
                renderMcpsDialog: "readonly",
                preRenderAgentsDialog: "readonly",
                renderAgentsDialog: "readonly",
                loadOmission: "readonly",
                loadMcp: "readonly",
                loadTool: "readonly",
                loadAgent: "readonly",
                loadMcps: "readonly",
                loadTools: "readonly",
                loadAgents: "readonly",

                // Cross-file globals: agent_page_context.js
                setContextButton: "readonly",
                unsetContextButton: "readonly",
                ClearContext: "readonly",

                // Cross-file globals: agent_page_chat.js
                appendChatMessage: "readonly",
                renderInitialMessages: "readonly",
                parseToFindFiles: "readonly",
                send2SaveFiles: "readonly",

                // Cross-file globals: agent_page_layout.js
                rotateTitle: "readonly",

                // Cross-file globals: agent_page_init.js
                Reconnect: "readonly",
                CleanHistory: "readonly",
                CancelAllAndLogout: "readonly",
                OpenOmissionsDialog: "readonly",
                OpenMcpsDialog: "readonly",
                OpenAgentsDialog: "readonly",
                OpenAboutDialog: "readonly",
                CloseAboutDialog: "readonly",
                listOllamaModels: "readonly",

                // Cross-file globals: variables (globals.js)
                generateUUID: "readonly",
                getHeaders: "readonly",
                SESSION_ID: "readonly",
                GLOBAL_STATE: "readonly",
                globalRunningState: "writable",
                titleBusyPrefix: "writable",
                isBusyProcessing: "writable",
                agentStatusPollerInterval: "writable",
                AGENT_STATUS_POLL_INTERVAL: "readonly",
                container: "readonly",
                canvas: "readonly",
                submonitor: "readonly",
                chat: "readonly",
                divider: "readonly",
                openBtn: "readonly",
                fileCloseBtn: "readonly",
                saveBtn: "readonly",
                filenameSpan: "readonly",
                btnStart: "readonly",
                btnStop: "readonly",
                btnPause: "readonly",
                btnClear: "readonly",
                btnValidate: "readonly",
                VALIDATION_STATE: "readonly",
                flowValidationStatus: "writable",
                pausedProcessesOnPause: "readonly",
                connections: "writable",
                itemCounters: "writable",
                nodeConfigs: "writable",
                selectedItems: "writable",
                hasUnsavedChanges: "writable",

                // Cross-file globals: undo_manager.js
                UndoManager: "readonly",
                undoManager: "readonly",

                // Cross-file globals: ui_manager.js
                markDirty: "readonly",
                markClean: "readonly",
                updateSaveButtonState: "readonly",

                // Cross-file globals: connection_graph.js
                getCenter: "readonly",
                setPathD: "readonly",
                createConnectionGroup: "readonly",
                updateAttachedConnections: "readonly",
                getAllUpstreamAgents: "readonly",
                findDownstreamEnders: "readonly",
                removeConnection: "readonly",
                removeConnectionsFor: "readonly",
                removeConnectionWithoutUndo: "readonly",
                captureConnectionState: "readonly",
                captureRelatedConnections: "readonly",
                recreateConnection: "readonly",

                // Cross-file globals: canvas_interaction.js
                makeDraggable: "readonly",
                applyAgentConnectionConfig: "readonly",

                // Cross-file globals: canvas_item_dialog.js
                preRenderCanvasItemDialog: "readonly",
                renderCanvasItemDialog: "readonly",

                // Cross-file globals: acp-globals.js
                ACP: "writable",
                isFlowCreatorWaiting: "writable",
                updateFilenameDisplay: "readonly",
                canvasContent: "readonly",
                updateCanvasContentSize: "readonly",

                // Cross-file globals: acp-running-state.js
                setGlobalRunningState: "readonly",
                pollAgentStatus: "readonly",
                updateControlButtonStates: "readonly",

                // Cross-file globals: acp-validate.js
                updateValidateButtonState: "readonly",
                showStartValidationCheckDialog: "readonly",
                resetFlowValidation: "readonly",

                // Cross-file globals: acp-agent-connectors.js
                registerItem: "readonly",
                updateRaiserConnection: "readonly",
                updateEmailerConnection: "readonly",
                updateMonitorLogConnection: "readonly",
                updateEnderConnection: "readonly",
                updateStarterConnection: "readonly",
                updateCronerConnection: "readonly",
                updateOrAgentConnection: "readonly",
                updateAndAgentConnection: "readonly",
                updateCleanerConnection: "readonly",
                updateMoverConnection: "readonly",
                updateSleeperConnection: "readonly",
                updateShoterConnection: "readonly",
                updateDeleterConnection: "readonly",
                updateExecuterConnection: "readonly",
                updateStopperConnection: "readonly",
                updatePythonxerConnection: "readonly",
                updateWhatsapperConnection: "readonly",
                updateAskerConnection: "readonly",
                updateForkerConnection: "readonly",
                updateNotifierConnection: "readonly",
                updateRecmailerConnection: "readonly",
                updateSsherConnection: "readonly",
                updateScperConnection: "readonly",
                updateSqlerConnection: "readonly",
                updatePrompterConnection: "readonly",
                updateTelegramrxConnection: "readonly",
                updateTelegramerConnection: "readonly",
                updateGitterConnection: "readonly",
                updateDockererConnection: "readonly",
                updatePserConnection: "readonly",
                updateKuberneterConnection: "readonly",
                updateApirerConnection: "readonly",
                updateJenkinserConnection: "readonly",
                updateCrawlerConnection: "readonly",
                updateSummarizerConnection: "readonly",
                updateMouserConnection: "readonly",
                updateCounterConnection: "readonly",

                // Cross-file globals: acp-canvas-core.js
                applyAgentTypeClass: "readonly",
                appendInputTriangles: "readonly",
                appendOutputTriangles: "readonly",
                appendLedIndicator: "readonly",
                createCanvasItem: "readonly",
                cloneAndRegister: "readonly",
                selectItem: "readonly",
                deselectAll: "readonly",
                toggleSelection: "readonly",
                selectConnection: "readonly",
                toggleConnectionSelection: "readonly",
                populateAgentsList: "readonly",
                loadAgentDescription: "readonly",
                initCanvasEvents: "readonly",

                // Cross-file globals: acp-canvas-undo.js
                captureItemState: "readonly",
                recreateCanvasItem: "readonly",
                deleteCanvasItemWithoutUndo: "readonly",

                // Cross-file globals: acp-file-io.js
                loadDiagram: "readonly",
                restoreAgentConnection: "readonly",
            },
        },

        rules: {
            // --- Possible Errors ---
            "no-console": "off",               // Allow console.log (needed for dev)
            "no-debugger": "warn",              // Warn on leftover debugger statements
            "no-duplicate-case": "error",       // Duplicate case labels
            "no-empty": "warn",                 // Empty block statements
            "no-extra-semi": "warn",            // Unnecessary semicolons
            "no-unreachable": "warn",           // Code after return/throw
            "no-unsafe-finally": "error",       // Unsafe finally blocks
            "valid-typeof": "error",            // Valid typeof comparisons

            // --- Best Practices ---
            "eqeqeq": ["warn", "smart"],        // Prefer === over == (smart allows == null)
            "no-eval": "error",                  // No eval()
            "no-implied-eval": "error",          // No implied eval (setTimeout with string)
            "no-self-assign": "warn",            // x = x
            "no-self-compare": "warn",           // x === x
            "no-unused-expressions": "warn",     // Unused expressions
            "no-useless-return": "warn",         // Unnecessary return statements
            "no-throw-literal": "warn",          // Only throw Error objects
            "no-loop-func": "warn",              // Functions inside loops
            "no-redeclare": ["warn", { "builtinGlobals": false }], // Variable redeclaration (ignore globals from config)
            "no-global-assign": "error",         // Don't overwrite builtins

            // --- Variables ---
            "no-unused-vars": ["warn", {
                "vars": "all",
                "args": "after-used",             // Only warn on unused args after last used
                "argsIgnorePattern": "^_",        // Ignore args prefixed with _
                "varsIgnorePattern": "^_",        // Ignore vars prefixed with _
                "ignoreRestSiblings": true,
                "caughtErrors": "none",           // Don't warn on unused catch params
            }],
            "no-use-before-define": "off",        // Off - our scripts rely on hoisting
            "no-shadow": "off",                   // Off - too noisy for browser globals pattern
            "no-undef": "error",                  // Catch typos and missing globals

            // --- Style (warnings, not errors) ---
            "no-trailing-spaces": "off",          // Don't enforce - let formatter handle
            "no-mixed-spaces-and-tabs": "warn",
            "no-var": "warn",                     // Prefer let/const over var
            "prefer-const": ["warn", {
                "destructuring": "all",
            }],
            "no-constant-condition": "warn",      // if (true) {}
        },
    },
];

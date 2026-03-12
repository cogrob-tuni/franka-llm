/**
 * Main Application Entry Point
 */

document.addEventListener('DOMContentLoaded', () => {
    // Initialize ROSBridge connection
    try {
        window.ros = new ROSBridge({ url: 'ws://localhost:9090' });
    } catch (error) {
        console.error('Failed to initialize ROSBridge:', error);
    }

    // Initialize modules
    window.chatModule = new ChatModule();
    window.statusModule = new StatusModule();

    // Navigation
    const navButtons = document.querySelectorAll('.nav-item');
    const views = document.querySelectorAll('.view-container');
    navButtons.forEach(button => {
        button.addEventListener('click', () => {
            const viewName = button.getAttribute('data-view');
            navButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            views.forEach(view => {
                view.classList.remove('active');
                if (view.id === `${viewName}View`) view.classList.add('active');
            });
        });
    });

    // Chat input
    const chatInput = document.getElementById('chatInput');
    const sendBtn = document.getElementById('sendBtn');
    sendBtn.addEventListener('click', () => {
        const message = chatInput.value.trim();
        if (message) {
            window.chatModule.sendMessage(message);
            chatInput.value = '';
            chatInput.focus();
        }
    });
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendBtn.click();
    });

    // Evaluation prompt picker
    // Same 5 prompts are used for every scene (single / multiple / overlapped)
    const EVAL_PROMPTS = {
        pick:     ['pick the yellow dice', 'grab the yellow dice', 'pick up the yellow dice not the red dice', 'can you pick up the yellow dice', 'I need you to pick the yellow dice'],
        place:    ['place it to the left of the red dice', 'put it to the right of the red dice', 'place it above the red dice', 'place it below the red dice', 'put it right side of the red dice'],
        handover: ['give it to me', 'hand it over', 'pass it to me', 'can you give me the dice', 'deliver the dice carefully to my hand'],
    };

    document.getElementById('evalInsertBtn').addEventListener('click', () => {
        const task  = document.getElementById('evalTask').value;
        const trial = document.getElementById('evalTrial').value;
        if (!task || trial === '') return;
        const prompt = EVAL_PROMPTS[task]?.[parseInt(trial)];
        if (prompt) {
            chatInput.value = prompt;
            chatInput.focus();
        }
    });

    // Status monitoring
    window.statusModule.startMonitoring();

    // Sidebar connection dot
    const updateConnectionStatus = () => {
        const connStatus = document.getElementById('connStatus');
        const statusText = document.querySelector('.status-text');
        if (window.ros && window.ros.isConnected()) {
            connStatus.className = 'status-dot connected';
            statusText.textContent = 'Connected';
        } else {
            connStatus.className = 'status-dot';
            statusText.textContent = 'Disconnected';
        }
    };
    updateConnectionStatus();
    setInterval(updateConnectionStatus, 1000);
});


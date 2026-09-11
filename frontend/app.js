// Smart Quiz Platform - Premium Sidebar Dashboard Logic

const BACKEND_URL = window.location.origin;

// App state
let quizQuestions = [];
let currentQuestionIndex = 0;
let score = 0;
let userAnswers = [];
let timerInterval = null;
let timeLeft = 30;
const QUESTION_TIME_LIMIT = 30; // 30 seconds per question
let selectedFile = null;
let currentUtterance = null;
let activeMode = 'topic'; // 'topic' or 'file'
let quizStartTime = null;
let quizOriginView = 'browse'; // Track where the quiz started from ('browse' or 'custom')

// Sidebar Menu Elements
const menuBrowse = document.getElementById('menu-browse');
const menuCustom = document.getElementById('menu-custom');
const menuLeaderboard = document.getElementById('menu-leaderboard');

// View Panel Elements
const browseView = document.getElementById('browse-view');
const setupView = document.getElementById('setup-view');
const leaderboardView = document.getElementById('leaderboard-view');
const loadingView = document.getElementById('loading-view');
const quizView = document.getElementById('quiz-view');
const resultView = document.getElementById('result-view');

// Setup screen elements
const topicInput = document.getElementById('topic-input');
const tagsPanel = document.getElementById('tags-panel');
const quickTags = document.querySelectorAll('.tag');
const difficultySelect = document.getElementById('difficulty-select');
const countSelect = document.getElementById('count-select');
const typeSelect = document.getElementById('type-select');
const languageSelect = document.getElementById('language-select');
const startBtn = document.getElementById('start-btn');

// Mode Tab Elements
const tabTopicBtn = document.getElementById('tab-topic-btn');
const tabFileBtn = document.getElementById('tab-file-btn');
const topicModeGroup = document.getElementById('topic-mode-group');
const fileModeGroup = document.getElementById('file-mode-group');

// File Upload Elements
const uploadArea = document.getElementById('upload-area');
const fileInput = document.getElementById('file-input');
const uploadStatusText = document.getElementById('upload-status-text');
const fileInfoContainer = document.getElementById('file-info-container');
const uploadedFileName = document.getElementById('uploaded-file-name');
const clearFileBtn = document.getElementById('clear-file-btn');
const uploadIcon = document.getElementById('upload-icon');

// Quiz screen elements
const progressBar = document.getElementById('progress-bar');
const currentQuestionNum = document.getElementById('current-question-num');
const totalQuestionsNum = document.getElementById('total-questions-num');
const timerText = document.getElementById('timer-text');
const questionText = document.getElementById('question-text');
const optionsContainer = document.getElementById('options-container');
const explanationBox = document.getElementById('explanation-box');
const explanationText = document.getElementById('explanation-text');
const nextBtn = document.getElementById('next-btn');
const prevBtn = document.getElementById('prev-btn');
const ttsBtn = document.getElementById('tts-btn');

// Result screen elements
const userScore = document.getElementById('user-score');
const totalScore = document.getElementById('total-score');
const accuracyValue = document.getElementById('accuracy-value');
const reviewList = document.getElementById('review-list');
const restartBtn = document.getElementById('restart-btn');
const resultBadgeContainer = document.getElementById('result-badge-container');
const resultTitle = document.getElementById('result-title');

// Certificate Elements
const certificateSection = document.getElementById('certificate-section');
const certNameInput = document.getElementById('cert-name-input');
const downloadCertBtn = document.getElementById('download-cert-btn');
const certCanvas = document.getElementById('certificate-canvas');

// Initialize App
document.addEventListener('DOMContentLoaded', () => {
    setupEventListeners();
    checkAuth();
    
    // Route to correct view if query param exists
    const urlParams = new URLSearchParams(window.location.search);
    const view = urlParams.get('view');
    if (view) {
        navigateToView(view);
    }
});

// Auth Check on load
function checkAuth() {
    const user = JSON.parse(localStorage.getItem('quiz_user'));
    const authNavItem = document.getElementById('auth-nav-item');
    const profileNavItem = document.getElementById('profile-nav-item');
    const userInfo = document.getElementById('user-info');
    const displayUsername = document.getElementById('display-username');
    const sidebarAvatar = document.getElementById('sidebar-avatar');

    if (user && user.username) {
        if (authNavItem) authNavItem.style.display = 'none';
        if (profileNavItem) profileNavItem.style.display = 'flex';
        if (userInfo) userInfo.style.display = 'block';
        if (displayUsername) displayUsername.textContent = user.username.charAt(0).toUpperCase() + user.username.slice(1);
        if (sidebarAvatar) sidebarAvatar.textContent = user.username.charAt(0).toUpperCase();
    } else {
        if (authNavItem) authNavItem.style.display = 'flex';
        if (profileNavItem) profileNavItem.style.display = 'none';
        if (userInfo) userInfo.style.display = 'none';
    }
}

function logout() {
    localStorage.removeItem('quiz_user');
    localStorage.removeItem('quiz_username');
    window.location.reload();
}
// Register on window object so dashboard logout button click handles it
window.logout = logout;

// Event Listeners Setup
function setupEventListeners() {
    // Sidebar Navigation Switching
    menuBrowse.addEventListener('click', () => switchSidebarView('browse'));
    menuCustom.addEventListener('click', () => switchSidebarView('custom'));
    menuLeaderboard.addEventListener('click', () => switchSidebarView('leaderboard'));

    // Mode Switch Tabs in Custom Setup
    tabTopicBtn.addEventListener('click', () => switchMode('topic'));
    tabFileBtn.addEventListener('click', () => switchMode('file'));

    // Quick Tag Selection
    quickTags.forEach(tag => {
        tag.addEventListener('click', () => {
            quickTags.forEach(t => t.classList.remove('active'));
            tag.classList.add('active');
            topicInput.value = tag.getAttribute('data-topic');
        });
    });

    // File drag and drop logic
    uploadArea.addEventListener('click', () => fileInput.click());
    
    fileInput.addEventListener('change', handleFileSelect);
    
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        if (e.dataTransfer.files.length > 0) {
            fileInput.files = e.dataTransfer.files;
            handleFileSelect();
        }
    });

    // Clear Uploaded File
    clearFileBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        resetFileUploader();
    });

    // Start Custom Quiz Button
    startBtn.addEventListener('click', () => {
        quizOriginView = 'custom';
        generateQuiz();
    });

    // Quiz Language Preference Sync (Both Browse view and Custom Setup view)
    const browseLangSelect = document.getElementById('browse-language-select');
    const savedLang = localStorage.getItem('quiz_language') || 'English';
    
    if (languageSelect) {
        languageSelect.value = savedLang;
        languageSelect.addEventListener('change', () => {
            localStorage.setItem('quiz_language', languageSelect.value);
            if (browseLangSelect) browseLangSelect.value = languageSelect.value;
        });
    }

    if (browseLangSelect) {
        browseLangSelect.value = savedLang;
        browseLangSelect.addEventListener('change', () => {
            localStorage.setItem('quiz_language', browseLangSelect.value);
            if (languageSelect) languageSelect.value = browseLangSelect.value;
        });
    }

    // Previous Question Button
    prevBtn.addEventListener('click', handlePrevQuestion);

    // Next Question Button
    nextBtn.addEventListener('click', handleNextQuestion);

    // Restart Quiz Button
    restartBtn.addEventListener('click', resetQuiz);

    // Text to Speech Button
    ttsBtn.addEventListener('click', toggleSpeech);

    // Certificate Download Button
    downloadCertBtn.addEventListener('click', downloadCertificate);

    // Confirmation Modal Actions
    document.getElementById('confirm-cancel-btn').addEventListener('click', hideConfirmModal);
    document.getElementById('confirm-yes-btn').addEventListener('click', () => {
        if (onConfirmCallback) onConfirmCallback();
        hideConfirmModal();
    });

    // Alert Modal Actions
    document.getElementById('alert-ok-btn').addEventListener('click', hideAlertModal);

    // Auth Wall Modal Actions
    document.getElementById('auth-wall-login-btn').addEventListener('click', () => {
        window.location.href = 'login.html';
    });
    document.getElementById('auth-wall-register-btn').addEventListener('click', () => {
        window.location.href = 'register.html';
    });
    document.getElementById('auth-wall-cancel-btn').addEventListener('click', hideAuthWall);
}

// Premium Custom Confirmation Modal State & Helpers
let onConfirmCallback = null;

function showConfirmModal(callback) {
    const modal = document.getElementById('confirm-modal');
    modal.classList.remove('hidden');
    // Force reflow
    modal.offsetHeight;
    modal.classList.add('active');
    onConfirmCallback = callback;
}

function hideConfirmModal() {
    const modal = document.getElementById('confirm-modal');
    modal.classList.remove('active');
    setTimeout(() => {
        modal.classList.add('hidden');
    }, 300);
    onConfirmCallback = null;
}

// Alert Modal Helpers
function showAlert(message, title = "Attention") {
    const modal = document.getElementById('alert-modal');
    document.getElementById('alert-modal-title').textContent = title;
    document.getElementById('alert-modal-message').textContent = message;
    modal.classList.remove('hidden');
    // Force reflow
    modal.offsetHeight;
    modal.classList.add('active');
}

function hideAlertModal() {
    const modal = document.getElementById('alert-modal');
    modal.classList.remove('active');
    setTimeout(() => {
        modal.classList.add('hidden');
    }, 300);
}

// Auth Wall (Login Required) Modal
function requireLogin() {
    const user = JSON.parse(localStorage.getItem('quiz_user'));
    if (user && user.username) return true; // logged in
    showAuthWall();
    return false;
}

function showAuthWall() {
    const modal = document.getElementById('auth-wall-modal');
    modal.classList.remove('hidden');
    modal.offsetHeight; // force reflow
    modal.classList.add('active');
}

function hideAuthWall() {
    const modal = document.getElementById('auth-wall-modal');
    modal.classList.remove('active');
    setTimeout(() => modal.classList.add('hidden'), 300);
}

// Sidebar view switching helper
function switchSidebarView(view) {
    if (quizView.classList.contains('active')) {
        showConfirmModal(() => {
            clearInterval(timerInterval);
            // Stop speaking just in case
            stopSpeech();
            // Proceed to the view
            navigateToView(view);
        });
        return;
    }
    
    navigateToView(view);
}

function navigateToView(view) {
    // Reset active class on menu items
    [menuBrowse, menuCustom, menuLeaderboard].forEach(m => m.classList.remove('active'));
    // Reset active class on view panels
    [browseView, setupView, leaderboardView, loadingView, quizView, resultView].forEach(v => v.classList.remove('active'));

    // Stop speaking just in case
    stopSpeech();

    if (view === 'browse') {
        menuBrowse.classList.add('active');
        browseView.classList.add('active');
    } else if (view === 'custom') {
        menuCustom.classList.add('active');
        setupView.classList.add('active');
    } else if (view === 'leaderboard') {
        menuLeaderboard.classList.add('active');
        leaderboardView.classList.add('active');
        loadLeaderboard();
    }
}

async function loadLeaderboard() {
    const rowsContainer = document.getElementById('leaderboard-rows');
    if (!rowsContainer) return;
    
    try {
        const response = await fetch('/api/leaderboard');
        const data = await response.json();
        
        if (data.success && data.leaderboard) {
            if (data.leaderboard.length === 0) {
                rowsContainer.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px; color: #64748b;">No quiz data yet. Be the first to appear on the leaderboard!</td></tr>';
                return;
            }
            
            rowsContainer.innerHTML = data.leaderboard.map((item, index) => {
                const rank = index + 1;
                let rankCell = '';
                let rowClass = '';
                
                if (rank === 1) {
                    rankCell = `<td><i class="fa-solid fa-trophy first-place"></i> 1</td>`;
                    rowClass = 'class="top-rank"';
                } else if (rank === 2) {
                    rankCell = `<td><i class="fa-solid fa-trophy second-place"></i> 2</td>`;
                    rowClass = 'class="top-rank"';
                } else if (rank === 3) {
                    rankCell = `<td><i class="fa-solid fa-trophy third-place"></i> 3</td>`;
                    rowClass = 'class="top-rank"';
                } else {
                    rankCell = `<td>${rank}</td>`;
                }
                
                const capitalizedUser = item.username.charAt(0).toUpperCase() + item.username.slice(1);
                const displayScore = item.score;
                const totalQ = item.total_questions || 5;
                const percentage = Math.round((displayScore / totalQ) * 100);
                const badgeClass = percentage >= 80 ? 'rank-1' : percentage >= 40 ? 'rank-2' : '';
                
                return `
                    <tr ${rowClass}>
                        ${rankCell}
                        <td style="font-weight: 600; color: #0f172a;">${capitalizedUser}</td>
                        <td style="text-transform: capitalize;">${item.category}</td>
                        <td style="font-weight: 700; color: ${percentage >= 80 ? '#16a34a' : percentage >= 40 ? '#d97706' : '#dc2626'}; font-size: 1.05rem;">${percentage}%</td>
                        <td><span class="rank-pill ${badgeClass}">${displayScore} / ${totalQ}</span></td>
                        <td>${item.time_taken}</td>
                    </tr>
                `;
            }).join('');
        } else {
            rowsContainer.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px; color: #ef4444;">Failed to load leaderboard.</td></tr>';
        }
    } catch (err) {
        console.error('Error fetching leaderboard:', err);
        rowsContainer.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 24px; color: #ef4444;">Error loading leaderboard.</td></tr>';
    }
}

// Exit quiz handler from quiz card
function confirmExitQuiz() {
    showConfirmModal(() => {
        clearInterval(timerInterval);
        stopSpeech();
        
        if (menuCustom.classList.contains('active')) {
            navigateToView('custom');
        } else if (menuLeaderboard.classList.contains('active')) {
            navigateToView('leaderboard');
        } else {
            navigateToView('browse');
        }
    });
}
window.confirmExitQuiz = confirmExitQuiz;

// Helper to switch view panels for quiz states
function showViewPanel(viewPanel) {
    [browseView, setupView, leaderboardView, loadingView, quizView, resultView].forEach(v => {
        v.classList.remove('active');
    });
    viewPanel.classList.add('active');
}

// Mode Switcher Function (Topic vs File in Setup)
function switchMode(mode) {
    activeMode = mode;
    if (mode === 'topic') {
        tabTopicBtn.classList.add('active');
        tabFileBtn.classList.remove('active');
        topicModeGroup.classList.remove('hidden');
        fileModeGroup.classList.add('hidden');
        resetFileUploader(); // Clear uploaded file when switching back
    } else {
        tabTopicBtn.classList.remove('active');
        tabFileBtn.classList.add('active');
        topicModeGroup.classList.add('hidden');
        fileModeGroup.classList.remove('hidden');
    }
}

// File Select Handler
function handleFileSelect() {
    const file = fileInput.files[0];
    if (!file) return;

    const name = file.name.toLowerCase();
    if (!name.endsWith('.pdf') && !name.endsWith('.txt')) {
        alert('Please upload only PDF or TXT files.');
        resetFileUploader();
        return;
    }

    selectedFile = file;
    uploadedFileName.textContent = file.name;
    
    // UI Updates
    fileInfoContainer.classList.remove('hidden');
    uploadIcon.className = "fa-solid fa-file-circle-check upload-box-icon";
    uploadIcon.style.color = "var(--success-color)";
    uploadStatusText.textContent = "File Selected successfully!";
    uploadStatusText.style.color = "var(--success-color)";
}

function resetFileUploader() {
    selectedFile = null;
    fileInput.value = '';
    fileInfoContainer.classList.add('hidden');
    uploadIcon.className = "fa-solid fa-file-pdf upload-box-icon";
    uploadIcon.style.color = "var(--primary-color)";
    uploadStatusText.textContent = "Drag & Drop or Click to Upload PDF/TXT";
    uploadStatusText.style.color = "var(--text-main)";
}

// Quick Quiz Start from Browse Grid Category Cards
async function startQuickQuiz(topic) {
    // Guard: must be logged in
    if (!requireLogin()) return;

    // Configure default quiz parameters
    topicInput.value = topic;
    difficultySelect.value = 'medium';
    countSelect.value = '5';
    typeSelect.value = 'mcq';
    if (languageSelect) {
        const savedLang = localStorage.getItem('quiz_language');
        if (!languageSelect.value && savedLang) {
            languageSelect.value = savedLang;
        } else if (!languageSelect.value) {
            languageSelect.value = 'English';
        }
    }
    activeMode = 'topic';
    quizOriginView = 'browse';
    
    // Switch to Topic view active state behind the scenes
    switchMode('topic');

    // Trigger quiz creation
    await generateQuiz();
}
// Register on window object so HTML onclick handles it
window.startQuickQuiz = startQuickQuiz;

// Generate Quiz FormData Call
async function generateQuiz() {
    // Guard: must be logged in
    if (!requireLogin()) return;

    const topic = topicInput.value.trim();
    const difficulty = difficultySelect.value;
    const count = parseInt(countSelect.value);
    const language = languageSelect.value;
    const quizType = typeSelect.value;

    // Mode-specific validation
    if (activeMode === 'topic' && !topic) {
        showAlert('Please enter or select a topic to begin.', 'Topic Required');
        return;
    }
    
    if (activeMode === 'file' && !selectedFile) {
        showAlert('Please upload a study document (PDF/TXT) to begin.', 'Document Required');
        return;
    }

    // Switch to Loading View
    showViewPanel(loadingView);

    // Build Form Data for file upload compatibility
    const formData = new FormData();
    formData.append('difficulty', difficulty);
    formData.append('count', count);
    formData.append('language', language);
    formData.append('quiz_type', quizType);
    
    if (activeMode === 'topic') {
        formData.append('topic', topic);
    } else {
        formData.append('topic', selectedFile.name);
        formData.append('file', selectedFile);
    }

    try {
        const response = await fetch(`${BACKEND_URL}/api/generate-quiz`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        
        if (data.success && data.questions && data.questions.length > 0) {
            quizQuestions = data.questions;
            totalQuestionsNum.textContent = quizQuestions.length;
            startQuizPlay();
        } else {
            console.error('Quiz Generation Error:', data);
            showAlert('Failed to generate quiz. Please check backend logs.', 'Generation Failed');
            showViewPanel(setupView);
        }
    } catch (err) {
        console.error('Fetch error:', err);
        showAlert('Could not connect to the backend server. Make sure Flask app.py is running!', 'Connection Error');
        showViewPanel(setupView);
    }
}

// Start playing
function startQuizPlay() {
    currentQuestionIndex = 0;
    score = 0;
    userAnswers = [];
    quizStartTime = Date.now();
    showViewPanel(quizView);
    loadQuestion();
}

// Load current question
function loadQuestion() {
    // Stop speaking immediately
    stopSpeech();
    
    explanationBox.classList.add('hidden');
    nextBtn.classList.add('hidden');
    prevBtn.classList.add('hidden');
    
    const question = quizQuestions[currentQuestionIndex];
    currentQuestionNum.textContent = currentQuestionIndex + 1;
    
    // Update progress bar
    const progressPercent = ((currentQuestionIndex) / quizQuestions.length) * 100;
    progressBar.style.width = `${progressPercent}%`;

    // Render Question
    questionText.textContent = question.question;

    // Render options
    optionsContainer.innerHTML = '';
    
    // Check if this question is already answered
    const answeredState = userAnswers[currentQuestionIndex];

    question.options.forEach((option) => {
        const button = document.createElement('button');
        button.className = 'option-btn';
        
        // Use textContent to safely render HTML tags as text
        const textSpan = document.createElement('span');
        textSpan.textContent = option;
        
        const badgeSpan = document.createElement('span');
        badgeSpan.className = 'option-badge';
        badgeSpan.innerHTML = '<i class="fa-solid fa-question"></i>';
        
        button.appendChild(textSpan);
        button.appendChild(badgeSpan);
        
        if (answeredState) {
            button.disabled = true;
            if (isAnswerMatch(option, answeredState.selected)) {
                if (answeredState.isCorrect) {
                    button.classList.add('correct');
                    badgeSpan.innerHTML = '<i class="fa-solid fa-check"></i>';
                } else {
                    button.classList.add('wrong');
                    badgeSpan.innerHTML = '<i class="fa-solid fa-xmark"></i>';
                }
            } else if (isAnswerMatch(option, answeredState.correct)) {
                button.classList.add('correct');
                badgeSpan.innerHTML = '<i class="fa-solid fa-check"></i>';
            }
        } else {
            button.addEventListener('click', () => handleOptionSelection(button, option));
        }
        
        optionsContainer.appendChild(button);
    });

    if (answeredState) {
        clearInterval(timerInterval);
        timerText.textContent = '--';
        showExplanation(answeredState.explanation);
        showNextButton();
    } else {
        // Start Timer
        resetTimer();
    }

    // Toggle Previous Button
    if (currentQuestionIndex > 0) {
        prevBtn.classList.remove('hidden');
    }
}

// Flexible Answer Matcher for Multilingual Quizzes
function isAnswerMatch(a, b) {
    if (a === undefined || a === null || b === undefined || b === null) return false;
    const strA = String(a).trim();
    const strB = String(b).trim();
    if (strA === strB) return true;
    if (strA.toLowerCase() === strB.toLowerCase()) return true;

    // Strip common option markers e.g. "A. ", "A) ", "(A) ", "1. ", "क. ", "ख) "
    const stripMarker = s => s.replace(/^([A-Da-d1-4कखगघ][\.\)\-\]]|\([A-Da-d1-4कखगघ]\))\s*/, '').trim();
    const cleanA = stripMarker(strA);
    const cleanB = stripMarker(strB);
    if (cleanA && cleanB && cleanA.toLowerCase() === cleanB.toLowerCase()) return true;

    // Normalize True/False variants across English and Hindi
    const trueEquivs = ['true', 'सत्य', 'सही', 'सच्चा'];
    const falseEquivs = ['false', 'असत्य', 'गलत', 'झूठा'];
    const lowA = cleanA.toLowerCase();
    const lowB = cleanB.toLowerCase();
    if (trueEquivs.includes(lowA) && trueEquivs.includes(lowB)) return true;
    if (falseEquivs.includes(lowA) && falseEquivs.includes(lowB)) return true;

    return false;
}

// Timer
function resetTimer() {
    clearInterval(timerInterval);
    timeLeft = QUESTION_TIME_LIMIT;
    timerText.textContent = timeLeft;
    
    timerInterval = setInterval(() => {
        timeLeft--;
        timerText.textContent = timeLeft;
        
        if (timeLeft <= 0) {
            clearInterval(timerInterval);
            handleTimeOut();
        }
    }, 1000);
}

// Timeout
function handleTimeOut() {
    const question = quizQuestions[currentQuestionIndex];
    
    userAnswers[currentQuestionIndex] = {
        question: question.question,
        selected: "No Answer (Time Out)",
        correct: question.correct_answer,
        isCorrect: false,
        explanation: question.explanation
    };

    handleNextQuestion();
}

// Option click
function handleOptionSelection(selectedBtn, selectedOption) {
    clearInterval(timerInterval);
    disableOptions();

    const question = quizQuestions[currentQuestionIndex];
    const isCorrect = isAnswerMatch(selectedOption, question.correct_answer);

    if (isCorrect) {
        selectedBtn.classList.add('correct');
        selectedBtn.querySelector('.option-badge').innerHTML = '<i class="fa-solid fa-check"></i>';
    } else {
        selectedBtn.classList.add('wrong');
        selectedBtn.querySelector('.option-badge').innerHTML = '<i class="fa-solid fa-xmark"></i>';
        highlightCorrectOption(question.correct_answer);
    }

    userAnswers[currentQuestionIndex] = {
        question: question.question,
        selected: selectedOption,
        correct: question.correct_answer,
        isCorrect: isCorrect,
        explanation: question.explanation
    };

    showExplanation(question.explanation);
    showNextButton();
}

function disableOptions() {
    const buttons = optionsContainer.querySelectorAll('.option-btn');
    buttons.forEach(btn => btn.disabled = true);
}

function highlightCorrectOption(correctAnswer) {
    const buttons = optionsContainer.querySelectorAll('.option-btn');
    buttons.forEach(btn => {
        const text = btn.querySelector('span').textContent;
        if (isAnswerMatch(text, correctAnswer)) {
            btn.classList.add('correct');
            btn.querySelector('.option-badge').innerHTML = '<i class="fa-solid fa-check"></i>';
        }
    });
}

function showExplanation(text) {
    explanationText.textContent = text || "No explanation provided.";
    explanationBox.classList.remove('hidden');
}

function showNextButton() {
    if (currentQuestionIndex === quizQuestions.length - 1) {
        nextBtn.querySelector('span').innerHTML = 'See Results &rarr;';
    } else {
        nextBtn.querySelector('span').innerHTML = 'Next Question &rarr;';
    }
    nextBtn.classList.remove('hidden');
}

function handleNextQuestion() {
    currentQuestionIndex++;
    if (currentQuestionIndex < quizQuestions.length) {
        loadQuestion();
    } else {
        showResults();
    }
}

function handlePrevQuestion() {
    if (currentQuestionIndex > 0) {
        currentQuestionIndex--;
        loadQuestion();
    }
}

// Audio Text to Speech Logic
function toggleSpeech() {
    if (window.speechSynthesis.speaking) {
        stopSpeech();
        return;
    }

    const textToRead = explanationText.textContent;
    if (!textToRead) return;

    currentUtterance = new SpeechSynthesisUtterance(textToRead);
    
    // Choose speech language accent
    const language = languageSelect.value.toLowerCase();
    if (language === 'hindi') {
        currentUtterance.lang = 'hi-IN';
    } else {
        currentUtterance.lang = 'en-US';
    }

    currentUtterance.onstart = () => {
        ttsBtn.classList.add('speaking');
        ttsBtn.innerHTML = '<i class="fa-solid fa-square"></i>';
    };

    currentUtterance.onend = () => {
        resetSpeechUI();
    };

    currentUtterance.onerror = () => {
        resetSpeechUI();
    };

    window.speechSynthesis.speak(currentUtterance);
}

// Stop Speech
function stopSpeech() {
    window.speechSynthesis.cancel();
    resetSpeechUI();
}

function resetSpeechUI() {
    ttsBtn.classList.remove('speaking');
    ttsBtn.innerHTML = '<i class="fa-solid fa-volume-high"></i>';
}

// Show Results & Cert check
function showResults() {
    stopSpeech();
    progressBar.style.width = `100%`;
    showViewPanel(resultView);
    
    const finalScore = userAnswers.filter(ans => ans && ans.isCorrect).length;
    
    userScore.textContent = finalScore;
    totalScore.textContent = quizQuestions.length;
    
    const accuracy = Math.round((finalScore / quizQuestions.length) * 100);
    accuracyValue.textContent = `${accuracy}%`;

    // Trophy styling
    if (accuracy >= 80) {
        resultTitle.textContent = "Outstanding Performance!";
        resultBadgeContainer.innerHTML = '<i class="fa-solid fa-trophy trophy-gold"></i>';
        
        // Show Certificate Section
        certificateSection.classList.remove('hidden');
        certNameInput.value = '';
    } else {
        if (accuracy >= 50) {
            resultTitle.textContent = "Good Effort!";
            resultBadgeContainer.innerHTML = '<i class="fa-solid fa-award" style="font-size:40px; color:#cbd5e1;"></i>';
        } else {
            resultTitle.textContent = "Keep Practicing!";
            resultBadgeContainer.innerHTML = '<i class="fa-solid fa-circle-question" style="font-size:40px; color:#ef4444;"></i>';
        }
        // Hide Certificate Section
        certificateSection.classList.add('hidden');
    }

    // Dynamic Review List
    reviewList.innerHTML = '';
    userAnswers.forEach((ans, index) => {
        if (!ans) return;
        const item = document.createElement('div');
        item.className = 'review-item';
        
        const badgeClass = ans.isCorrect ? 'correct' : 'wrong';
        const badgeIcon = ans.isCorrect ? '<i class="fa-solid fa-check"></i> Correct' : '<i class="fa-solid fa-xmark"></i> Incorrect';
        
        item.innerHTML = `
            <div class="review-question">${index + 1}. ${escapeHTML(ans.question)}</div>
            <div class="review-answer-status">
                <span class="review-badge ${badgeClass}">${badgeIcon}</span>
                <p><strong>Your Answer:</strong> <span>${escapeHTML(ans.selected)}</span></p>
                ${!ans.isCorrect ? `<p><strong>Correct Answer:</strong> <span style="color: var(--success-color); font-weight: 600;">${escapeHTML(ans.correct)}</span></p>` : ''}
            </div>
            <div class="review-exp">
                <strong>AI Explanation:</strong> ${escapeHTML(ans.explanation)}
            </div>
        `;
        reviewList.appendChild(item);
    });

    // Save score to database if logged in
    const user = JSON.parse(localStorage.getItem('quiz_user'));
    if (user && user.username) {
        let category = 'General Knowledge';
        if (activeMode === 'topic') {
            category = topicInput.value || 'General Knowledge';
        } else if (selectedFile) {
            category = selectedFile.name;
        }

        let timeTaken = '0:00';
        if (quizStartTime) {
            const diffMs = Date.now() - quizStartTime;
            const totalSecs = Math.floor(diffMs / 1000);
            const mins = Math.floor(totalSecs / 60);
            const secs = totalSecs % 60;
            timeTaken = `${mins}:${secs < 10 ? '0' : ''}${secs}`;
        }

        // Post score
        fetch('/api/save-score', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                username: user.username,
                category: category,
                score: finalScore,
                total_questions: quizQuestions.length,
                time_taken: timeTaken
            })
        }).catch(err => console.error('Failed to save score:', err));
    }
}

// HTML5 Canvas Certificate Generator
function drawCertificate(name) {
    const ctx = certCanvas.getContext('2d');
    const w = certCanvas.width;
    const h = certCanvas.height;

    // 1. Light blue-grey background matching template
    ctx.fillStyle = '#e9f1f7'; 
    ctx.fillRect(0, 0, w, h);

    // Left and Right blue decorative border strips
    const stripWidth = w * 0.02;
    ctx.fillStyle = '#1e3a8a'; // Deep blue
    ctx.fillRect(0, 0, stripWidth, h);
    ctx.fillStyle = '#2563eb'; // Royal blue
    ctx.fillRect(w - stripWidth, 0, stripWidth, h);

    // 2. White Card Center Area with rounded corners and border
    const marginX = w * 0.05;
    const marginY = h * 0.06;
    ctx.fillStyle = '#ffffff';
    ctx.beginPath();
    ctx.roundRect(marginX, marginY, w - (marginX * 2), h - (marginY * 2), w * 0.025);
    ctx.fill();
    ctx.strokeStyle = '#cbd5e1';
    ctx.lineWidth = w * 0.0015;
    ctx.stroke();

    // 3. Content Text Align
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';

    // 4. Header: "Certificate of Achievement"
    ctx.fillStyle = '#b45309'; // Warm Bronze-Gold
    ctx.font = `italic bold ${Math.round(h * 0.038)}px Georgia, serif`;
    ctx.fillText('Certificate of Achievement', w / 2, h * 0.16);

    // 5. Sub-header: "THIS IS TO CERTIFY THAT"
    ctx.fillStyle = '#64748b'; // Slate gray
    ctx.font = `bold ${Math.round(h * 0.02)}px "Outfit", sans-serif`;
    ctx.fillText('THIS IS TO CERTIFY THAT', w / 2, h * 0.24);

    // 6. Recipient Name
    ctx.fillStyle = '#0f172a'; // Deep Black-Charcoal
    ctx.font = `bold ${Math.round(h * 0.07)}px Georgia, serif`;
    ctx.fillText(name.toUpperCase(), w / 2, h * 0.35);

    // Accent line under name with center diamond
    const lineWidth = w * 0.22;
    const lineY = h * 0.41;
    ctx.beginPath();
    ctx.moveTo(w / 2 - lineWidth, lineY);
    ctx.lineTo(w / 2 - (w * 0.02), lineY);
    ctx.moveTo(w / 2 + (w * 0.02), lineY);
    ctx.lineTo(w / 2 + lineWidth, lineY);
    ctx.lineWidth = w * 0.0015;
    ctx.strokeStyle = '#cbd5e1';
    ctx.stroke();
    
    // Draw center gold diamond
    ctx.fillStyle = '#d97706';
    ctx.beginPath();
    const diaSize = w * 0.009;
    ctx.moveTo(w / 2, lineY - diaSize);
    ctx.lineTo(w / 2 + diaSize, lineY);
    ctx.lineTo(w / 2, lineY + diaSize);
    ctx.lineTo(w / 2 - diaSize, lineY);
    ctx.closePath();
    ctx.fill();

    // 7. Description: "has successfully completed the learning assessment on the topic:"
    ctx.fillStyle = '#475569';
    ctx.font = `italic ${Math.round(h * 0.027)}px Georgia, serif`;
    ctx.fillText('has successfully completed the learning assessment on the topic:', w / 2, h * 0.48);

    // 8. Topic
    const topic = activeMode === 'topic' ? (topicInput.value || "General Knowledge") : (selectedFile ? selectedFile.name : "Uploaded Document");
    ctx.fillStyle = '#2563eb'; // Royal Blue
    ctx.font = `bold ${Math.round(h * 0.04)}px Georgia, serif`;
    ctx.fillText(`"${topic}"`, w / 2, h * 0.56);

    // 9. Date and Issuer Details
    const today = new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    ctx.font = `${Math.round(h * 0.022)}px "Outfit", sans-serif`;
    ctx.fillStyle = '#0f172a';
    
    const infoY = h * 0.77;
    const lineTopY = h * 0.74;

    // Left: Date
    ctx.fillText(today, w * 0.3, infoY);
    ctx.beginPath();
    ctx.moveTo(w * 0.2, lineTopY);
    ctx.lineTo(w * 0.4, lineTopY);
    ctx.lineWidth = w * 0.0015;
    ctx.strokeStyle = '#cbd5e1';
    ctx.stroke();
    
    ctx.fillStyle = '#64748b';
    ctx.fillText('Date Issued', w * 0.3, h * 0.81);

    // Right: Issuer Signature
    ctx.fillStyle = '#0f172a';
    ctx.fillText('Smart Quiz Platform', w * 0.7, infoY);
    ctx.beginPath();
    ctx.moveTo(w * 0.6, lineTopY);
    ctx.lineTo(w * 0.8, lineTopY);
    ctx.lineWidth = w * 0.0015;
    ctx.strokeStyle = '#cbd5e1';
    ctx.stroke();
    
    ctx.fillStyle = '#64748b';
    ctx.fillText('Certified Issuer', w * 0.7, h * 0.81);

    // 10. Center Wax-Style Gold Seal
    const sealX = w / 2;
    const sealY = h * 0.76;
    const outerSealRadius = h * 0.053;
    const innerSealRadius = h * 0.043;
    
    // Outer scalloped gold circle
    ctx.fillStyle = '#d97706';
    ctx.beginPath();
    ctx.arc(sealX, sealY, outerSealRadius, 0, Math.PI * 2);
    ctx.fill();

    // Inner gold circle
    ctx.fillStyle = '#b45309';
    ctx.beginPath();
    ctx.arc(sealX, sealY, innerSealRadius, 0, Math.PI * 2);
    ctx.fill();

    // Center star vector
    drawStar(ctx, sealX, sealY, 5, outerSealRadius * 0.45, innerSealRadius * 0.23);
}

// Vector Star drawing helper function
function drawStar(ctx, cx, cy, spikes, outerRadius, innerRadius) {
    let rot = Math.PI / 2 * 3;
    let x = cx;
    let y = cy;
    let step = Math.PI / spikes;

    ctx.beginPath();
    ctx.moveTo(cx, cy - outerRadius);
    for (let i = 0; i < spikes; i++) {
        x = cx + Math.cos(rot) * outerRadius;
        y = cy + Math.sin(rot) * outerRadius;
        ctx.lineTo(x, y);
        rot += step;

        x = cx + Math.cos(rot) * innerRadius;
        y = cy + Math.sin(rot) * innerRadius;
        ctx.lineTo(x, y);
        rot += step;
    }
    ctx.lineTo(cx, cy - outerRadius);
    ctx.closePath();
    ctx.fillStyle = '#ffffff';
    ctx.fill();
}

// Download Certificate PDF
function downloadCertificate() {
    const nameInput = document.getElementById('cert-name-input');
    const name = nameInput.value.trim();
    
    if (!name) {
        showAlert('Please type your name first.', 'Name Required');
        nameInput.focus();
        return;
    }
    
    // Draw on the canvas
    drawCertificate(name);

    // Get image data from Canvas
    const imgData = certCanvas.toDataURL('image/png');

    // Initialize jsPDF
    const { jsPDF } = window.jspdf;
    const pdf = new jsPDF({
        orientation: 'landscape',
        unit: 'mm',
        format: [297, 210] // A4 Size Landscape
    });

    // Add image to PDF. Fits perfectly on A4 landscape.
    pdf.addImage(imgData, 'PNG', 0, 0, 297, 210);

    // Save as PDF
    pdf.save(`Certificate_${name.replace(/\s+/g, '_')}.pdf`);
}

// Reset app state
function resetQuiz() {
    stopSpeech();
    quizQuestions = [];
    currentQuestionIndex = 0;
    score = 0;
    userAnswers = [];
    resetFileUploader();
    
    if (menuCustom.classList.contains('active')) {
        navigateToView('custom');
    } else if (menuLeaderboard.classList.contains('active')) {
        navigateToView('leaderboard');
    } else {
        navigateToView('browse');
    }
}

// HTML Escaping Helper to prevent tag rendering issues
function escapeHTML(str) {
    if (!str) return '';
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}




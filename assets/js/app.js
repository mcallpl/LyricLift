const urlInput = document.getElementById('urlInput');
const fileInput = document.getElementById('fileInput');
const dropzone = document.getElementById('dropzone');
const fileName = document.getElementById('fileName');
const extractBtn = document.getElementById('extractBtn');
const loadingState = document.getElementById('loadingState');
const loadingMessage = document.getElementById('loadingMessage');
const resultsSection = document.getElementById('resultsSection');
const resultsTextarea = document.getElementById('resultsTextarea');
const copyBtn = document.getElementById('copyBtn');
const downloadBtn = document.getElementById('downloadBtn');
const errorState = document.getElementById('errorState');
const errorMessage = document.getElementById('errorMessage');
const backBtn = document.getElementById('backBtn');

let currentJobId = null;
let currentFileName = null;
let droppedFile = null;
let statusPollTimer = null;

const allowedExtensions = ['mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm'];
const allowedMimeTypes = [
    'audio/mpeg',
    'audio/mp3',
    'audio/mp4',
    'audio/m4a',
    'audio/x-m4a',
    'audio/wav',
    'audio/x-wav',
    'audio/wave',
    'video/mp4',
    'video/quicktime',
    'video/webm'
];

function isValidMediaFile(file) {
    const extension = file.name.split('.').pop().toLowerCase();
    return allowedExtensions.includes(extension) || allowedMimeTypes.includes(file.type);
}

function stripHtml(text) {
    return text
        .replace(/<script[\s\S]*?<\/script>/gi, ' ')
        .replace(/<style[\s\S]*?<\/style>/gi, ' ')
        .replace(/<[^>]*>/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
}

function describeHttpError(response, bodyText) {
    if (response.status === 502 || response.status === 503 || response.status === 504) {
        return 'The server stopped responding while processing. Your file may be too long for the current server capacity.';
    }

    const summary = stripHtml(bodyText).slice(0, 220);
    if (summary) {
        return `Server returned HTTP ${response.status}: ${summary}`;
    }

    return `Server returned HTTP ${response.status}. Please try again.`;
}

async function readJsonResponse(response) {
    const bodyText = await response.text();

    try {
        const data = bodyText ? JSON.parse(bodyText) : {};
        if (!response.ok && !data.error) {
            throw new Error(describeHttpError(response, bodyText));
        }
        return data;
    } catch (error) {
        if (error instanceof SyntaxError) {
            throw new Error(describeHttpError(response, bodyText));
        }
        throw error;
    }
}

function setProcessing(isProcessing) {
    extractBtn.disabled = isProcessing;
    extractBtn.textContent = isProcessing ? 'Processing...' : 'Extract Words';
}

function clearStatusPoll() {
    if (statusPollTimer) {
        clearTimeout(statusPollTimer);
        statusPollTimer = null;
    }
}

function updateLoadingMessage(status, message) {
    if (message) {
        loadingMessage.textContent = message;
        return;
    }

    const messages = {
        queued: 'Queued for processing...',
        downloading: 'Downloading audio...',
        processing: 'Processing...',
        transcribing: 'Transcribing audio...'
    };

    loadingMessage.textContent = messages[status] || 'Processing...';
}

// Dropzone handling
dropzone.addEventListener('click', () => fileInput.click());

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('dragover');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('dragover');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('dragover');
    handleFileSelect(e.dataTransfer.files);
});

fileInput.addEventListener('change', (e) => {
    handleFileSelect(e.target.files);
});

function handleFileSelect(files) {
    if (files.length === 0) return;

    const file = files[0];

    if (!isValidMediaFile(file)) {
        droppedFile = null;
        fileInput.value = '';
        fileName.textContent = '';
        fileName.style.display = 'none';
        showError('Invalid file type. Please upload: MP3, MP4, M4A, WAV, MOV, or WEBM');
        return;
    }

    // Store the file for later use
    droppedFile = file;

    // Clear URL input
    urlInput.value = '';
    fileName.textContent = `Selected: ${file.name} (${formatFileSize(file.size)})`;
    fileName.style.display = 'block';
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

extractBtn.addEventListener('click', () => {
    const url = urlInput.value.trim();
    const format = document.querySelector('input[name="format"]:checked').value;
    const selectedFile = droppedFile || (fileInput.files.length > 0 ? fileInput.files[0] : null);

    if (!url && !selectedFile) {
        showError('Please enter a URL or upload a file');
        return;
    }

    if (url && selectedFile) {
        showError('Please provide either a URL or a file, not both');
        return;
    }

    extract(url, selectedFile, format);
});

async function extract(url, file, format) {
    clearStatusPoll();
    showLoading('Starting extraction...');

    const formData = new FormData();
    if (url) {
        formData.append('url', url);
    } else if (file) {
        formData.append('file', file);
    }
    formData.append('format', format);

    try {
        const response = await fetch('/extract', {
            method: 'POST',
            body: formData
        });

        const data = await readJsonResponse(response);

        if (data.jobId && data.status === 'processing') {
            currentJobId = data.jobId;
            updateLoadingMessage(data.status, data.message);
            pollJobStatus(data.jobId);
        } else if (data.success && data.text) {
            showCompletedResult(data);
        } else {
            showError(data.error || 'Processing failed');
        }
    } catch (error) {
        showError(error.message);
    }
}

function pollJobStatus(jobId, attempt = 0) {
    const maxAttempts = 720; // one hour at five-second intervals

    statusPollTimer = setTimeout(async () => {
        try {
            const response = await fetch(`/status/${encodeURIComponent(jobId)}?t=${Date.now()}`);
            const data = await readJsonResponse(response);

            if (data.status === 'done' && data.success) {
                showCompletedResult(data);
                return;
            }

            if (data.status === 'error' || data.success === false) {
                showError(data.error || 'Processing failed');
                return;
            }

            if (attempt >= maxAttempts) {
                showError('Processing is taking longer than expected. Please try a shorter file or split the recording into smaller parts.');
                return;
            }

            updateLoadingMessage(data.status, data.message);
            pollJobStatus(jobId, attempt + 1);
        } catch (error) {
            showError(`Error checking processing status: ${error.message}`);
        }
    }, attempt === 0 ? 1000 : 5000);
}

function showCompletedResult(data) {
    currentFileName = data.filename;
    resultsTextarea.value = data.text;
    showResults();
}

function showLoading(message) {
    hideAllStates();
    if (message) {
        loadingMessage.textContent = message;
    }
    setProcessing(true);
    loadingState.classList.remove('hidden');
}

function showResults() {
    clearStatusPoll();
    hideAllStates();
    setProcessing(false);
    resultsSection.classList.remove('hidden');
}

function showError(msg) {
    clearStatusPoll();
    hideAllStates();
    setProcessing(false);
    errorMessage.textContent = msg;
    errorState.classList.remove('hidden');
}

function hideAllStates() {
    loadingState.classList.add('hidden');
    resultsSection.classList.add('hidden');
    errorState.classList.add('hidden');
}

copyBtn.addEventListener('click', () => {
    resultsTextarea.select();
    document.execCommand('copy');

    const originalText = copyBtn.textContent;
    copyBtn.textContent = 'Copied!';
    setTimeout(() => {
        copyBtn.textContent = originalText;
    }, 2000);
});

downloadBtn.addEventListener('click', () => {
    if (!currentFileName || !resultsTextarea.value) {
        showError('No file available to download');
        return;
    }

    const blob = new Blob([resultsTextarea.value], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = currentFileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
});

async function deleteTemporaryFile(jobId) {
    try {
        const response = await fetch('delete.php', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ jobId: jobId })
        });
        const result = await response.json();
        if (result.success) {
            console.log('Temporary file deleted');
        } else {
            console.error('Error deleting temporary file:', result.error || response.statusText);
        }
    } catch (error) {
        console.error('Error deleting temporary file:', error);
    }
}

backBtn.addEventListener('click', () => {
    clearStatusPoll();
    urlInput.value = '';
    fileInput.value = '';
    fileName.textContent = '';
    fileName.style.display = 'none';
    resultsTextarea.value = '';
    currentJobId = null;
    currentFileName = null;
    droppedFile = null;
    setProcessing(false);
    hideAllStates();
});

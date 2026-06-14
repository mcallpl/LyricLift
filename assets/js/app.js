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
    showLoading();

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

        const data = await response.json();

        if (data.success) {
            currentJobId = 'transcription';
            currentFileName = data.filename;
            resultsTextarea.value = data.text;
            showResults();
        } else {
            showError(data.error || 'Processing failed');
        }
    } catch (error) {
        showError('Error: ' + error.message);
    }
}

function startLoadingMessageCycle() {
    let index = 0;
    const interval = setInterval(() => {
        if (!loadingState.classList.contains('hidden')) {
            loadingMessage.textContent = loadingMessages[index % loadingMessages.length];
            index++;
        } else {
            clearInterval(interval);
        }
    }, 2000);
}

function showLoading() {
    hideAllStates();
    loadingState.classList.remove('hidden');
}

function showResults() {
    hideAllStates();
    resultsSection.classList.remove('hidden');

    // Ask if user wants to delete the temporary file (only for file uploads)
    if (droppedFile && currentJobId) {
        setTimeout(() => {
            if (confirm(`Delete the temporary processing file?\n\n(Your original file is safe on your computer)`)) {
                deleteTemporaryFile(currentJobId);
            }
        }, 500);
    }
}

function showError(msg) {
    hideAllStates();
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
    if (!currentFileName) {
        showError('No file available to download');
        return;
    }

    const link = document.createElement('a');
    link.href = `download.php?file=${encodeURIComponent(currentFileName)}&job=${encodeURIComponent(currentJobId)}`;
    link.download = currentFileName;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
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
        }
    } catch (error) {
        console.error('Error deleting temporary file:', error);
    }
}

backBtn.addEventListener('click', () => {
    urlInput.value = '';
    fileInput.value = '';
    fileName.textContent = '';
    fileName.style.display = 'none';
    resultsTextarea.value = '';
    droppedFile = null;
    hideAllStates();
});

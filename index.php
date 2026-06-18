<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LyricLift - Extract Lyrics & Transcripts</title>
    <meta name="description" content="Extract lyrics, captions, and transcripts from any video or audio file. Supports YouTube, Facebook, Instagram, Vimeo, and direct file uploads.">
    <meta name="keywords" content="lyrics extraction, transcription, audio extraction, video transcription">

    <!-- Favicon -->
    <link rel="icon" type="image/x-icon" href="assets/images/favicon.ico">
    <link rel="apple-touch-icon" href="assets/images/favicon.png">

    <!-- Open Graph / Social Media Tags -->
    <meta property="og:type" content="website">
    <meta property="og:url" content="https://lyriclift.com">
    <meta property="og:title" content="LyricLift - Extract Lyrics & Transcripts">
    <meta property="og:description" content="Extract lyrics, captions, and transcripts from any video or audio file instantly.">
    <meta property="og:image" content="https://lyriclift.com/assets/images/social-preview.png">
    <meta property="og:image:width" content="1200">
    <meta property="og:image:height" content="630">

    <!-- Twitter Card Tags -->
    <meta name="twitter:card" content="summary_large_image">
    <meta name="twitter:title" content="LyricLift - Extract Lyrics & Transcripts">
    <meta name="twitter:description" content="Extract lyrics, captions, and transcripts from any video or audio file instantly.">
    <meta name="twitter:image" content="https://lyriclift.com/assets/images/social-preview.png">

    <link rel="stylesheet" href="assets/css/style.css">
</head>
<body>
    <div class="container">
        <header>
            <h1>⚡ LyricLift</h1>
            <p class="subtitle">Extract words and lyrics from any video or audio</p>
        </header>

        <main class="card">
            <!-- Input Section -->
            <div class="input-section">
                <div>
                    <label for="urlInput">Paste URL</label>
                    <input
                        type="text"
                        id="urlInput"
                        placeholder="Paste any video or audio URL (YouTube, Facebook, Instagram, Vimeo, etc.)"
                        class="input-field"
                    >
                </div>

                <div class="divider">OR</div>

                <div>
                    <label for="fileInput">Upload Audio/Video File</label>
                    <div id="dropzone" class="dropzone">
                        <input
                            type="file"
                            id="fileInput"
                            accept=".mp3,.mp4,.m4a,.wav,.mov,.webm"
                            class="file-input"
                        >
                        <p>Click to upload or drag & drop</p>
                        <p class="small">Supported: MP3, MP4, M4A, WAV, MOV, WEBM</p>
                        <p id="fileName" class="file-name"></p>
                    </div>
                </div>

                <!-- Format Selection -->
                <div class="format-section">
                    <p>Output Format:</p>
                    <label class="radio-label">
                        <input type="radio" name="format" value="srt" checked>
                        <span>With Timestamps (SRT)</span>
                    </label>
                    <label class="radio-label">
                        <input type="radio" name="format" value="txt">
                        <span>Plain Text Only</span>
                    </label>
                </div>

                <!-- Extract Button -->
                <button id="extractBtn" class="btn-primary">Extract Words</button>
            </div>

            <!-- Loading State -->
            <div id="loadingState" class="loading-state hidden">
                <div class="spinner"></div>
                <p id="loadingMessage">Processing (may take several minutes)...</p>
            </div>

            <!-- Results Section -->
            <div id="resultsSection" class="results-section hidden">
                <label for="resultsTextarea">Extracted Text:</label>
                <textarea
                    id="resultsTextarea"
                    class="results-textarea"
                    readonly
                ></textarea>

                <div class="button-group">
                    <button id="copyBtn" class="btn-secondary">Copy to Clipboard</button>
                    <button id="downloadBtn" class="btn-secondary">Download File</button>
                </div>
            </div>

            <!-- Error State -->
            <div id="errorState" class="error-state hidden">
                <p id="errorMessage"></p>
                <button id="backBtn" class="btn-secondary">Back</button>
            </div>
        </main>
    </div>

    <script src="assets/js/app.js?v=20260614-no-timeout"></script>
</body>
</html>

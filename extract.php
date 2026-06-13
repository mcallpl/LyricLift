<?php
ini_set('max_execution_time', 30);
ini_set('memory_limit', '256M');
header('Content-Type: application/json');

function stripAnsiCodes($string) {
    return preg_replace('/\x1b\[[0-9;]*m/', '', $string);
}

function generateJobId() {
    return uniqid('job_', true) . '_' . bin2hex(random_bytes(4));
}

$tmpDir = __DIR__ . '/tmp';
if (!is_dir($tmpDir)) {
    mkdir($tmpDir, 0775, true);
}

$url = isset($_POST['url']) ? trim($_POST['url']) : null;
$format = isset($_POST['format']) ? $_POST['format'] : 'srt';
$jobId = generateJobId();

if (!in_array($format, ['srt', 'txt'])) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'Invalid format']);
    exit;
}

$outputFormat = ($format === 'srt') ? 'srt' : 'txt';
$outputExt = ($format === 'srt') ? 'srt' : 'txt';

try {
    $MAX_SIZE = 104857600; // 100MB
    $statusFile = $tmpDir . '/' . $jobId . '.status';
    $audioPath = null;

    // FAST VALIDATION PHASE
    if ($url) {
        if (!filter_var($url, FILTER_VALIDATE_URL)) {
            throw new Exception('Invalid URL');
        }
        // Don't download yet - just validate
        file_put_contents($statusFile, 'downloading');
    } elseif (isset($_FILES['file']) && $_FILES['file']['error'] === UPLOAD_ERR_OK) {
        if ($_FILES['file']['size'] > $MAX_SIZE) {
            throw new Exception('File too large (max 30MB)');
        }

        $validExts = ['mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm'];
        $ext = strtolower(pathinfo($_FILES['file']['name'], PATHINFO_EXTENSION));
        if (!in_array($ext, $validExts)) {
            throw new Exception('Invalid file type');
        }

        $audioPath = $tmpDir . '/' . $jobId . '.' . $ext;
        if (!move_uploaded_file($_FILES['file']['tmp_name'], $audioPath)) {
            throw new Exception('Failed to save file');
        }
        file_put_contents($statusFile, 'transcribing');
    } else {
        throw new Exception('No URL or file provided');
    }

    // RETURN IMMEDIATELY - start background processing
    echo json_encode([
        'success' => true,
        'jobId' => $jobId,
        'status' => 'processing'
    ]);

    // BACKGROUND PROCESSING - continues even after response sent
    flush();
    ob_flush();

    // Create a script that will run in background
    $scriptPath = $tmpDir . '/' . $jobId . '_process.php';
    $scriptContent = <<<'EOFSCRIPT'
<?php
$jobId = $argv[1];
$tmpDir = $argv[2];
$url = $argv[3];
$format = $argv[4];

$outputFormat = ($format === 'srt') ? 'srt' : 'txt';
$outputExt = ($format === 'srt') ? 'srt' : 'txt';
$statusFile = $tmpDir . '/' . $jobId . '.status';
$audioPath = null;

function safeExec($cmd) {
    return shell_exec($cmd . ' 2>&1');
}

try {
    // Download or use existing file
    if ($url) {
        $audioPath = $tmpDir . '/' . $jobId . '.m4a';
        $dlCmd = 'python3 -m yt_dlp -f bestaudio -x --audio-format m4a --audio-quality 192K -o "' . $audioPath . '" "' . escapeshellarg($url) . '" 2>&1';
        safeExec($dlCmd);

        if (!file_exists($audioPath)) {
            file_put_contents($statusFile, 'error:Download failed');
            exit;
        }
    } else {
        // Find the uploaded file
        $exts = ['mp3', 'mp4', 'm4a', 'wav', 'mov', 'webm'];
        foreach ($exts as $ext) {
            $testPath = $tmpDir . '/' . $jobId . '.' . $ext;
            if (file_exists($testPath)) {
                $audioPath = $testPath;
                break;
            }
        }
    }

    if (!$audioPath || !file_exists($audioPath)) {
        file_put_contents($statusFile, 'error:No audio file');
        exit;
    }

    // Transcribe with Whisper
    file_put_contents($statusFile, 'transcribing');

    $cacheDir = dirname(__DIR__) . '/.cache';
    $outputPath = $tmpDir . '/' . $jobId;

    $whisperCmd = 'nice -n -10 bash -c "PYTHONHTTPSVERIFY=0 XDG_CACHE_HOME=\"' . $cacheDir . '\" python3 -m whisper \"' . $audioPath . '\" --model tiny --language English --output_format ' . $outputFormat . ' -o \"' . $tmpDir . '\" --device cpu --no_speech_threshold 0.1" 2>&1';

    $output = safeExec($whisperCmd);

    $expectedFile = $outputPath . '.' . $outputExt;
    if (!file_exists($expectedFile)) {
        file_put_contents($statusFile, 'error:Transcription failed');
        exit;
    }

    // Success
    file_put_contents($statusFile, 'done');

    // Clean up audio
    @unlink($audioPath);

} catch (Exception $e) {
    file_put_contents($statusFile, 'error:' . $e->getMessage());
}
EOFSCRIPT;

    file_put_contents($scriptPath, $scriptContent);

    // Run in background
    $bgCmd = 'nohup php ' . escapeshellarg($scriptPath) . ' ' . escapeshellarg($jobId) . ' ' . escapeshellarg($tmpDir) . ' ' . escapeshellarg($url) . ' ' . escapeshellarg($format) . ' > /dev/null 2>&1 &';
    shell_exec($bgCmd);

    // Cleanup old files
    $cutoff = time() - 1800;
    if ($handle = opendir($tmpDir)) {
        while (false !== ($file = readdir($handle))) {
            $path = $tmpDir . '/' . $file;
            if (is_file($path) && filemtime($path) < $cutoff) {
                @unlink($path);
            }
        }
        closedir($handle);
    }

} catch (Exception $e) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => $e->getMessage()]);
}

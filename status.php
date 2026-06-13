<?php
header('Content-Type: application/json');

$jobId = isset($_GET['job']) ? basename($_GET['job']) : null;
if (!$jobId) {
    echo json_encode(['success' => false, 'error' => 'No job ID']);
    exit;
}

$tmpDir = __DIR__ . '/tmp';
$statusFile = $tmpDir . '/' . $jobId . '.status';

if (!file_exists($statusFile)) {
    echo json_encode(['status' => 'unknown']);
    exit;
}

$status = trim(file_get_contents($statusFile));

// Check if done
if ($status === 'done') {
    // Find output file
    foreach (['srt', 'txt'] as $ext) {
        $outputFile = $tmpDir . '/' . $jobId . '.' . $ext;
        if (file_exists($outputFile)) {
            $text = file_get_contents($outputFile);
            // Remove ANSI codes
            $text = preg_replace('/\x1b\[[0-9;]*m/', '', $text);
            $text = trim($text);

            if (empty($text)) {
                echo json_encode(['status' => 'error', 'error' => 'No speech detected']);
                exit;
            }

            echo json_encode([
                'status' => 'done',
                'success' => true,
                'jobId' => $jobId,
                'filename' => 'transcription_' . date('Y-m-d_H-i-s') . '.' . $ext,
                'text' => $text
            ]);
            exit;
        }
    }

    echo json_encode(['status' => 'error', 'error' => 'Output file not found']);
    exit;
}

// Check if error
if (strpos($status, 'error:') === 0) {
    $error = substr($status, 6);
    echo json_encode(['status' => 'error', 'error' => $error]);
    exit;
}

// Still processing
echo json_encode(['status' => $status]);

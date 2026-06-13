<?php
header('Content-Type: application/json');

$tmpDir = __DIR__ . '/tmp';
$data = json_decode(file_get_contents('php://input'), true);

if (!isset($data['jobId'])) {
    http_response_code(400);
    echo json_encode(['success' => false, 'error' => 'No jobId provided']);
    exit;
}

$jobId = basename($data['jobId']);

// Find and delete the temporary audio file (could be .mp4, .m4a, .wav, etc.)
$extensions = ['mp4', 'm4a', 'mp3', 'wav', 'mov', 'webm'];
$deleted = false;

foreach ($extensions as $ext) {
    $filePath = $tmpDir . '/' . $jobId . '.' . $ext;
    if (file_exists($filePath)) {
        if (@unlink($filePath)) {
            $deleted = true;
        }
    }
}

if ($deleted) {
    echo json_encode(['success' => true]);
} else {
    echo json_encode(['success' => false, 'error' => 'File not found']);
}

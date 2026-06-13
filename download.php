<?php
header('Content-Type: application/octet-stream');

$tmpDir = __DIR__ . '/tmp';
$jobId = isset($_GET['job']) ? basename($_GET['job']) : null;
$filename = isset($_GET['file']) ? basename($_GET['file']) : null;

if (!$jobId || !$filename) {
    http_response_code(400);
    die('Invalid download request');
}

// Determine file extension
$ext = pathinfo($filename, PATHINFO_EXTENSION);
if (!in_array($ext, ['srt', 'txt'])) {
    http_response_code(400);
    die('Invalid file type');
}

// Find the actual output file
$outputFile = $tmpDir . '/' . $jobId . '.' . $ext;

if (!file_exists($outputFile)) {
    http_response_code(404);
    die('File not found');
}

// Serve the file
header('Content-Disposition: attachment; filename="' . $filename . '"');
header('Content-Length: ' . filesize($outputFile));

readfile($outputFile);
exit;

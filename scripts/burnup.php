<?php
function loadEnv($path) {
    if (!file_exists($path)) return;
    foreach (file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES) as $line) {
        if (strpos(trim($line), '#') === 0) continue; // skip comments
        list($name, $value) = explode('=', $line, 2);
        putenv("$name=$value");
        $_ENV[$name] = $value;
    }
}

loadEnv(__DIR__ . '/.env');

// ── Verify Slack request signature ─────────────────────────────────────────
$signing_secret = getenv('SIGNING_SECRET');
$timestamp = isset($_SERVER['HTTP_X_SLACK_REQUEST_TIMESTAMP']) ? $_SERVER['HTTP_X_SLACK_REQUEST_TIMESTAMP'] : '';
$sig_header = isset($_SERVER['HTTP_X_SLACK_SIGNATURE']) ? $_SERVER['HTTP_X_SLACK_SIGNATURE'] : '';
$body = file_get_contents('php://input');

if (!$signing_secret || !$timestamp || !$sig_header) {
    http_response_code(403);
    exit;
}

// Reject requests older than 5 minutes (replay protection)
if (abs(time() - intval($timestamp)) > 300) {
    http_response_code(403);
    exit;
}

$sig_basestring = "v0:$timestamp:$body";
$computed_sig = 'v0=' . hash_hmac('sha256', $sig_basestring, $signing_secret);

if (!hash_equals($computed_sig, $sig_header)) {
    http_response_code(403);
    exit;
}

$github_token = getenv('GITHUB_PAT');

$issueKey = isset($_POST['text']) ? trim($_POST['text']) : "";
$channelId = isset($_POST['channel_id']) ? $_POST['channel_id'] : "";

$jsonObj = new stdClass();
$jsonObj->response_type = "in_channel";

// Basic format validation (no API call — Jira validation happens in the workflow)
if (!preg_match('/^[A-Z][A-Z0-9]+-\d+$/', $issueKey)) {
    $jsonObj->text = "⚠️ Invalid issue key format: `$issueKey`. Expected format: `PROJ-123`.";
    header('Content-Type: application/json');
    echo json_encode($jsonObj);
    exit;
}

// Dispatch GitHub Action — Jira validation and Slack error reporting happen in the workflow
$github_repo = getenv('REPO');
$workflow = "burnup.yml";
$branch = "main";
$payload = json_encode([
    "ref" => $branch,
    "inputs" => [
        "issueKey" => $issueKey,
        "channel"  => $channelId
    ]
]);

$gh = curl_init("https://api.github.com/repos/$github_repo/actions/workflows/$workflow/dispatches");
curl_setopt($gh, CURLOPT_CUSTOMREQUEST, "POST");
curl_setopt($gh, CURLOPT_POSTFIELDS, $payload);
curl_setopt($gh, CURLOPT_RETURNTRANSFER, true);
curl_setopt($gh, CURLOPT_HTTPHEADER, [
    "Authorization: token $github_token",
    "Accept: application/vnd.github.v3+json",
    "User-Agent: slack-burnup-bot"
]);

curl_exec($gh);
$gh_code = curl_getinfo($gh, CURLINFO_HTTP_CODE);
curl_close($gh);

if ($gh_code >= 200 && $gh_code < 300) {
    $jsonObj->text = "I'm on it! Please give me a minute to build the plot for $issueKey.";
} else {
    $jsonObj->text = "⚠️ Failed to trigger GitHub Action for $issueKey. (HTTP $gh_code)";
}

header('Content-Type: application/json');
echo json_encode($jsonObj);
?>

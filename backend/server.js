const express = require("express");
const cors = require("cors");
const path = require("node:path");
const fs = require("node:fs");
const { spawn } = require("node:child_process");

const app = express();
const PORT = process.env.PORT || 5000;

const PYTHON_DIR = path.resolve(__dirname, "../python-automation");
const PYTHON_SCRIPT = path.join(PYTHON_DIR, "main.py");
const OUTPUT_DIR = path.join(PYTHON_DIR, "output");

// On Windows, "python" is usually appropriate.
// You can override this with PYTHON_EXECUTABLE if needed.
const PYTHON_EXECUTABLE = process.env.PYTHON_EXECUTABLE || "python";

const allowedOrigins = [
  "http://localhost:5173",
  process.env.FRONTEND_URL,
].filter(Boolean);

app.use(
  cors({
    origin(origin, callback) {
      if (!origin || allowedOrigins.includes(origin)) {
        return callback(null, true);
      }

      return callback(new Error("Origin not allowed by CORS"));
    },
  }),
);
app.use(express.json());

function isValidDate(value) {
  if (typeof value !== "string") return false;
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;

  const parsed = new Date(`${value}T00:00:00.000Z`);

  return (
    !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
  );
}

app.get("/api/health", (req, res) => {
  res.json({ success: true, message: "API is running." });
});

app.post("/api/reports", (req, res) => {
  const { reportDate } = req.body || {};

  if (!isValidDate(reportDate)) {
    return res.status(400).json({
      success: false,
      message: "Please provide a valid date in YYYY-MM-DD format.",
    });
  }

  if (!fs.existsSync(PYTHON_SCRIPT)) {
    return res.status(500).json({
      success: false,
      message: "Python automation script was not found.",
    });
  }

  const child = spawn(PYTHON_EXECUTABLE, [PYTHON_SCRIPT, reportDate], {
    cwd: PYTHON_DIR,
    windowsHide: true,
    env: {
      ...process.env,
      PYTHONUNBUFFERED: "1",
    },
  });

  let stdout = "";
  let stderr = "";
  let timedOut = false;
  let responded = false;

  // A slow hosted website should not keep a request running forever.
  const timeout = setTimeout(
    () => {
      timedOut = true;
      child.kill();
    },
    5 * 60 * 1000,
  );

  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });

  child.stderr.on("data", (chunk) => {
    stderr += chunk.toString();
  });

  child.on("error", (error) => {
    clearTimeout(timeout);
    responded = true;

    return res.status(500).json({
      success: false,
      message:
        `Could not start Python. Check the Python installation and ` +
        `PYTHON_EXECUTABLE setting. Details: ${error.message}`,
    });
  });

  child.on("close", (code) => {
    clearTimeout(timeout);

    if (responded) return;
    responded = true;

    if (timedOut) {
      return res.status(504).json({
        success: false,
        message: "The automation timed out after five minutes.",
      });
    }

    if (code !== 0) {
      console.error("Python automation failed.");
      console.error("Python stdout:\n", stdout);
      console.error("Python stderr:\n", stderr);

      return res.status(500).json({
        success: false,
        message: "Report generation failed.",
        details: (stderr || stdout || "No error details available.").slice(
          -8000,
        ),
      });
    }

    const resultLine = stdout
      .split(/\r?\n/)
      .find((line) => line.startsWith("RESULT_JSON:"));

    if (!resultLine) {
      return res.status(500).json({
        success: false,
        message: "Python finished but did not return a valid result.",
      });
    }

    let result;

    try {
      result = JSON.parse(resultLine.slice("RESULT_JSON:".length));
    } catch {
      return res.status(500).json({
        success: false,
        message: "Could not parse the Python result.",
      });
    }

    if (!result.success || !result.filename) {
      return res.status(500).json({
        success: false,
        message: "The Python script did not return a valid output file.",
      });
    }

    // Only allow a plain filename from the Python output.
    const filename = path.basename(result.filename);

    if (filename !== result.filename || !filename.endsWith(".csv")) {
      return res.status(500).json({
        success: false,
        message: "Python returned an invalid output filename.",
      });
    }

    const outputPath = path.resolve(OUTPUT_DIR, filename);

    if (
      !outputPath.startsWith(OUTPUT_DIR + path.sep) ||
      !fs.existsSync(outputPath)
    ) {
      return res.status(500).json({
        success: false,
        message: "The processed CSV could not be found.",
      });
    }

    return res.json({
      success: true,
      message: "Report generated successfully.",
      reportDate: result.reportDate,
      rowsProcessed: result.rowsProcessed,
      filename,
      downloadUrl: `/api/reports/download/${encodeURIComponent(filename)}`,
    });
  });
});

app.get("/api/reports/download/:filename", (req, res) => {
  const filename = req.params.filename;

  // Reject paths and unexpected filenames.
  if (
    path.basename(filename) !== filename ||
    !/^[a-zA-Z0-9_.-]+\.csv$/.test(filename)
  ) {
    return res.status(400).json({
      success: false,
      message: "Invalid filename.",
    });
  }

  const filePath = path.resolve(OUTPUT_DIR, filename);

  if (!filePath.startsWith(OUTPUT_DIR + path.sep) || !fs.existsSync(filePath)) {
    return res.status(404).json({
      success: false,
      message: "Report file not found.",
    });
  }

  return res.download(filePath, filename);
});

app.listen(PORT, () => {
  console.log(`Backend running at http://localhost:${PORT}`);
});

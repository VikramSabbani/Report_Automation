import { useState } from "react";

const API_URL = (
  import.meta.env.VITE_API_URL || "http://localhost:5000"
).replace(/\/$/, "");

function formatDate(dateString) {
  if (!dateString) return "";
  return new Date(`${dateString}T00:00:00`).toLocaleDateString("en-IN", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

export default function App() {
  const [reportDate, setReportDate] = useState(
    new Date().toLocaleDateString("en-CA"),
  );
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  async function generateReport(event) {
    event.preventDefault();

    setLoading(true);
    setResult(null);
    setError("");

    try {
      const response = await fetch(`${API_URL}/api/reports`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ reportDate }),
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        throw new Error(
          data.details
            ? `${data.message} ${data.details}`
            : data.message || "Could not generate the report.",
        );
      }

      setResult(data);
    } catch (err) {
      setError(
        err.message ||
          "Could not connect to the backend. Check whether it is running.",
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href="/">
          <span className="brand-mark">R</span>
          <span>ReportFlow</span>
        </a>

        <div className="connection-status">
          <span className="status-dot" />
          Automation workspace
        </div>
      </header>

      <main className="main-content">
        <div className="eyebrow">
          <span className="eyebrow-line" />
          REPORT AUTOMATION
        </div>

        <section className="intro">
          <h1>
            Your reports,
            <br />
            <span>without the busywork.</span>
          </h1>
          <p>
            Select a report date and let the automation handle downloading,
            processing, and preparing your CSV.
          </p>
        </section>

        <section className="workspace">
          <div className="workspace-header">
            <div className="section-icon" aria-hidden="true">
              <svg
                width="23"
                height="23"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.7"
              >
                <rect x="3" y="5" width="18" height="16" rx="3" />
                <path d="M16 3v4M8 3v4M3 10h18" />
              </svg>
            </div>

            <div>
              <h2>Generate a report</h2>
              <p>Choose the date for the report you need.</p>
            </div>
          </div>

          <form onSubmit={generateReport}>
            <label htmlFor="reportDate">Report date</label>

            <input
              id="reportDate"
              type="date"
              value={reportDate}
              onChange={(event) => setReportDate(event.target.value)}
              required
              disabled={loading}
            />

            <button
              type="submit"
              className="generate-button"
              disabled={loading || !reportDate}
            >
              {loading ? (
                <>
                  <span className="spinner" />
                  Generating report...
                </>
              ) : (
                <>
                  Generate report
                  <span aria-hidden="true">→</span>
                </>
              )}
            </button>
          </form>

          <div className="workflow">
            <div className="workflow-step">
              <span className="step-number">01</span>
              <span>Download CSV</span>
            </div>
            <span className="workflow-arrow">→</span>
            <div className="workflow-step">
              <span className="step-number">02</span>
              <span>Process data</span>
            </div>
            <span className="workflow-arrow">→</span>
            <div className="workflow-step">
              <span className="step-number">03</span>
              <span>Save report</span>
            </div>
          </div>
        </section>

        {loading && (
          <section className="notice loading-notice" aria-live="polite">
            <span className="spinner dark-spinner" />
            <div>
              <strong>Your report is being prepared</strong>
              <p>
                The automation is accessing the source website and processing
                the CSV. This may take a few minutes.
              </p>
            </div>
          </section>
        )}

        {error && (
          <section className="notice error-notice" role="alert">
            <span className="notice-symbol">!</span>
            <div>
              <strong>Report generation failed</strong>
              <p>{error}</p>
            </div>
          </section>
        )}

        {result && (
          <section className="result-card" aria-live="polite">
            <div className="success-heading">
              <span className="success-icon">✓</span>
              <div>
                <h2>Report generated successfully</h2>
                <p>Your processed CSV is ready to download.</p>
              </div>
            </div>

            <div className="result-details">
              <div>
                <span>Report date</span>
                <strong>{formatDate(result.reportDate)}</strong>
              </div>
              <div>
                <span>Rows processed</span>
                <strong>{result.rowsProcessed}</strong>
              </div>
              <div>
                <span>File type</span>
                <strong>CSV</strong>
              </div>
            </div>

            <a
              className="download-button"
              href={`${API_URL}${result.downloadUrl}`}
            >
              <svg
                width="19"
                height="19"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
              >
                <path d="M12 3v12m-5-5 5 5 5-5" />
                <path d="M5 17v4h14v-4" />
              </svg>
              Download processed CSV
            </a>

            <p className="filename">{result.filename}</p>
          </section>
        )}

        <section className="info-strip">
          <span className="info-icon">i</span>
          <p>
            The original downloaded CSV is preserved. Processing adds the{" "}
            <strong>Actual sale</strong> and <strong>Transaction Type</strong>{" "}
            columns to a new file.
          </p>
        </section>

        <footer>
          <span>ReportFlow</span>
          <span>Python · Node.js · React</span>
        </footer>
      </main>
    </div>
  );
}

import React from 'react';

/**
 * ErrorBoundary — catches unhandled JS errors in child components
 * and shows a recovery UI instead of a white screen.
 * 
 * Usage: <ErrorBoundary><Routes>...</Routes></ErrorBoundary>
 */

function ErrorFallback({ error, onReset }) {
  return (
    <div style={styles.container}>
      <div style={styles.card}>
        <div style={styles.iconRow}>
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="#F87171" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
        </div>
        <h2 style={styles.title}>Something went wrong</h2>
        <p style={styles.message}>
          This page encountered an unexpected error. Your data is safe.
        </p>
        {error && (
          <p style={styles.errorName}>
            {error.name}: {error.message}
          </p>
        )}
        <div style={styles.actions}>
          <button style={styles.btnPrimary} onClick={() => window.location.reload()}>
            Reload Page
          </button>
          <button style={styles.btnSecondary} onClick={onReset}>
            Try Again
          </button>
        </div>
      </div>
    </div>
  );
}

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[Leomail] UI crash caught by ErrorBoundary:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <ErrorFallback
          error={this.state.error}
          onReset={() => this.setState({ hasError: false, error: null })}
        />
      );
    }
    return this.props.children;
  }
}

// Inline styles to avoid depending on external CSS (must work even if CSS fails)
const styles = {
  container: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: '60vh',
    padding: '40px 20px',
  },
  card: {
    background: 'rgba(8, 12, 22, 0.94)',
    border: '1px solid rgba(248, 113, 113, 0.2)',
    borderRadius: '14px',
    padding: '40px',
    maxWidth: '440px',
    width: '100%',
    textAlign: 'center',
    backdropFilter: 'blur(16px)',
    boxShadow: '0 4px 24px rgba(0, 0, 0, 0.6), 0 0 20px rgba(248, 113, 113, 0.05)',
  },
  iconRow: {
    marginBottom: '16px',
  },
  title: {
    fontSize: '1.2em',
    fontWeight: 800,
    color: '#EDF2F7',
    marginBottom: '8px',
    letterSpacing: '0.3px',
  },
  message: {
    fontSize: '0.88em',
    color: '#A0AEC0',
    marginBottom: '12px',
    lineHeight: 1.5,
  },
  errorName: {
    fontSize: '0.75em',
    fontFamily: "'JetBrains Mono', monospace",
    color: '#F87171',
    background: 'rgba(248, 113, 113, 0.08)',
    padding: '8px 12px',
    borderRadius: '6px',
    marginBottom: '20px',
    wordBreak: 'break-word',
    textAlign: 'left',
  },
  actions: {
    display: 'flex',
    gap: '10px',
    justifyContent: 'center',
  },
  btnPrimary: {
    padding: '10px 20px',
    fontSize: '0.9em',
    fontWeight: 700,
    color: '#020a04',
    background: 'linear-gradient(135deg, #10B981 0%, #22D3EE 40%, #818CF8 75%, #A78BFA 100%)',
    border: 'none',
    borderRadius: '6px',
    cursor: 'pointer',
    fontFamily: 'inherit',
    letterSpacing: '0.3px',
    boxShadow: '0 3px 12px rgba(16, 185, 129, 0.25)',
  },
  btnSecondary: {
    padding: '10px 20px',
    fontSize: '0.9em',
    fontWeight: 700,
    color: '#A0AEC0',
    background: 'rgba(12, 16, 24, 0.9)',
    border: '1px solid rgba(16, 185, 129, 0.1)',
    borderRadius: '6px',
    cursor: 'pointer',
    fontFamily: 'inherit',
    letterSpacing: '0.3px',
  },
};

export default ErrorBoundary;

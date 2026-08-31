/**
 * RedactPro — Processing & Scanning Animation Controller with Real Backend Frame Progress
 */

class RedactionAnimation {
  constructor(options) {
    this.stageTextEl = options.stageTextEl;
    this.filenameEl = options.filenameEl;
    this.estimateTextEl = options.estimateTextEl || document.getElementById('estimate-text');
    this.countdownEl = options.countdownEl || document.getElementById('estimate-countdown');
    this.progressBarFill = document.getElementById('progress-bar-fill');

    this.stages = [
      'Processing securely',
      'Detecting sensitive information...',
      'Applying redactions...',
      'Preparing secure output...'
    ];

    this.currentStageIndex = 0;
    this.stageIntervalId = null;
    this.hasLiveProgress = false;
  }

  start(file) {
    this.stop();
    this.currentStageIndex = 0;
    this.hasLiveProgress = false;

    const filename = file ? file.name : 'Analyzing file...';
    if (this.filenameEl) {
      this.filenameEl.textContent = filename;
    }

    if (this.estimateTextEl) {
      this.estimateTextEl.textContent = 'Calculating frame analysis...';
    }
    if (this.countdownEl) {
      this.countdownEl.textContent = 'Estimating speed & remaining frames...';
    }
    if (this.progressBarFill) {
      this.progressBarFill.classList.add('progress-bar-indeterminate');
      this.progressBarFill.style.width = '';
    }

    this._updateText();

    // Rotate subtitle stages if no live progress received yet
    this.stageIntervalId = setInterval(() => {
      if (!this.hasLiveProgress) {
        this.currentStageIndex = (this.currentStageIndex + 1) % this.stages.length;
        this._updateText();
      }
    }, 1800);
  }

  /**
   * Update live with actual calculated frame/page progress from backend
   */
  updateProgress(data) {
    if (!data) return;
    this.hasLiveProgress = true;

    // 1. Stage Text
    if (this.stageTextEl && data.stage) {
      this.stageTextEl.textContent = data.stage;
    }

    // 2. Percentage & Progress Bar
    if (data.percent !== undefined && data.percent !== null && this.progressBarFill) {
      this.progressBarFill.classList.remove('progress-bar-indeterminate');
      this.progressBarFill.style.width = `${Math.min(100, Math.max(0, data.percent))}%`;
    }

    // 3. Exact Estimated Remaining Time calculation
    if (this.estimateTextEl) {
      if (data.eta_sec !== null && data.eta_sec !== undefined && data.eta_sec > 0) {
        this.estimateTextEl.textContent = `Est. remaining: ~${data.eta_sec.toFixed(1)}s`;
      } else if (data.percent >= 99) {
        this.estimateTextEl.textContent = 'Finalizing web output...';
      } else {
        this.estimateTextEl.textContent = 'Analyzing frames...';
      }
    }

    // 4. Detailed frame count and FPS stats
    if (this.countdownEl) {
      if (data.total_frames && data.processed_frames !== undefined) {
        const fpsText = data.fps ? ` at ${data.fps} FPS` : '';
        const pct = data.percent !== undefined ? ` (${data.percent}%)` : '';
        this.countdownEl.textContent = `${data.processed_frames} / ${data.total_frames} frames processed${pct}${fpsText}`;
      } else if (data.stage) {
        this.countdownEl.textContent = data.stage;
      }
    }
  }

  _updateText() {
    if (this.stageTextEl && !this.hasLiveProgress) {
      this.stageTextEl.textContent = this.stages[this.currentStageIndex];
    }
  }

  stop() {
    if (this.stageIntervalId) {
      clearInterval(this.stageIntervalId);
      this.stageIntervalId = null;
    }
    this.hasLiveProgress = false;
  }
}

window.RedactionAnimation = RedactionAnimation;

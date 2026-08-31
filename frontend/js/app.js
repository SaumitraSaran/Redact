/**
 * RedactPro — Main Application Controller
 * Manages the state machine: IDLE -> SELECTED -> PROCESSING -> COMPLETED | ERROR
 */

(function () {
  'use strict';

  // State definitions
  const State = {
    IDLE: 'IDLE',
    SELECTED: 'SELECTED',
    PROCESSING: 'PROCESSING',
    COMPLETED: 'COMPLETED',
    ERROR: 'ERROR'
  };

  class RedactProApp {
    constructor() {
      this.state = State.IDLE;

      // DOM Elements
      this.dom = {
        dropzone: document.getElementById('dropzone'),
        fileInput: document.getElementById('file-input'),
        dropzoneIdle: document.getElementById('dropzone-idle'),
        fileCard: document.getElementById('file-card'),
        fileNameDisplay: document.getElementById('file-name-display'),
        fileSpecsDisplay: document.getElementById('file-specs-display'),
        fileBadge: document.getElementById('file-badge'),
        removeBtn: document.getElementById('remove-file-btn'),
        instructionsInput: document.getElementById('instructions-input'),
        redactBtn: document.getElementById('redact-btn'),
        
        // Preview State Views
        previewStatusLabel: document.getElementById('preview-status-label'),
        stateIdle: document.getElementById('state-idle'),
        stateProcessing: document.getElementById('state-processing'),
        stateCompleted: document.getElementById('state-completed'),
        stateError: document.getElementById('state-error'),

        // Processing Elements
        stageTextEl: document.getElementById('processing-stage-text'),
        filenameEl: document.getElementById('processing-filename'),

        // Completed Elements
        mediaContainer: document.getElementById('media-container'),
        videoChunksBar: document.getElementById('video-chunks-bar'),
        chunksList: document.getElementById('chunks-list'),
        downloadBtn: document.getElementById('download-btn'),
        metaStats: document.getElementById('completion-meta-stats'),
        resetBtn: document.getElementById('reset-btn'),

        // Error Elements
        errorMessageText: document.getElementById('error-message-text'),
        errorResetBtn: document.getElementById('error-reset-btn')
      };

      // Initialize Sub-controllers
      this.animation = new RedactionAnimation({
        stageTextEl: this.dom.stageTextEl,
        filenameEl: this.dom.filenameEl
      });

      this.preview = new PreviewController({
        mediaContainer: this.dom.mediaContainer,
        chunksBar: this.dom.videoChunksBar,
        chunksList: this.dom.chunksList,
        downloadBtn: this.dom.downloadBtn,
        metaStats: this.dom.metaStats
      });

      this.upload = new UploadController({
        dropzone: this.dom.dropzone,
        fileInput: this.dom.fileInput,
        dropzoneIdle: this.dom.dropzoneIdle,
        fileCard: this.dom.fileCard,
        fileNameDisplay: this.dom.fileNameDisplay,
        fileSpecsDisplay: this.dom.fileSpecsDisplay,
        fileBadge: this.dom.fileBadge,
        removeBtn: this.dom.removeBtn,
        onFileSelected: (file) => this.onFileSelected(file),
        onFileRemoved: () => this.onFileRemoved()
      });

      this._bindGlobalEvents();
      this.setState(State.IDLE);
    }

    _bindGlobalEvents() {
      // Redact button click
      this.dom.redactBtn.addEventListener('click', () => {
        this.startRedaction();
      });

      // Reset buttons
      this.dom.resetBtn.addEventListener('click', () => {
        this.resetAll();
      });

      this.dom.errorResetBtn.addEventListener('click', () => {
        this.setState(State.SELECTED);
      });
    }

    setState(newState, payload = {}) {
      this.state = newState;

      // Update panel status label
      const statusLabels = {
        [State.IDLE]: 'Awaiting input',
        [State.SELECTED]: 'Ready for redaction',
        [State.PROCESSING]: 'Confidential processing in progress',
        [State.COMPLETED]: 'Redaction complete',
        [State.ERROR]: 'Processing error'
      };
      this.dom.previewStatusLabel.textContent = statusLabels[newState] || '';

      // Manage view visibility
      this.dom.stateIdle.classList.toggle('hidden', newState !== State.IDLE);
      this.dom.stateProcessing.classList.toggle('hidden', newState !== State.PROCESSING);
      this.dom.stateCompleted.classList.toggle('hidden', newState !== State.COMPLETED);
      this.dom.stateError.classList.toggle('hidden', newState !== State.ERROR);

      // Manage controls
      if (newState === State.IDLE) {
        this.dom.redactBtn.disabled = true;
        this.dom.instructionsInput.disabled = false;
        this.animation.stop();
        this.preview.clear();
      } else if (newState === State.SELECTED) {
        this.dom.redactBtn.disabled = false;
        this.dom.instructionsInput.disabled = false;
        this.animation.stop();
      } else if (newState === State.PROCESSING) {
        this.dom.redactBtn.disabled = true;
        this.dom.instructionsInput.disabled = true;
        this.animation.start(payload.file);
      } else if (newState === State.COMPLETED) {
        this.dom.redactBtn.disabled = false;
        this.dom.instructionsInput.disabled = false;
        this.animation.stop();
        if (payload.data) {
          this.preview.render(payload.data);
        }
      } else if (newState === State.ERROR) {
        this.dom.redactBtn.disabled = false;
        this.dom.instructionsInput.disabled = false;
        this.animation.stop();
        this.dom.errorMessageText.textContent = payload.message || 'An error occurred during redaction.';
      }
    }

    onFileSelected(file) {
      this.setState(State.SELECTED);
    }

    onFileRemoved() {
      this.setState(State.IDLE);
    }

    resetAll() {
      this.upload.clearFile();
      this.dom.instructionsInput.value = '';
      this.setState(State.IDLE);
      fetch('/api/clear-temp', { method: 'POST' }).catch(() => {});
    }

    async startRedaction() {
      const file = this.upload.getFile();
      if (!file) return;

      const instructions = this.dom.instructionsInput.value.trim();
      const jobId = 'job_' + Date.now() + '_' + Math.random().toString(36).substring(2, 9);

      // Transition to processing state
      this.setState(State.PROCESSING, { file: file, filename: file.name });

      // Construct FormData
      const formData = new FormData();
      formData.append('file', file);
      formData.append('job_id', jobId);
      if (instructions) {
        formData.append('instructions', instructions);
      }

      // Live progress polling loop
      let isProcessing = true;
      const pollProgress = async () => {
        while (isProcessing) {
          try {
            const res = await fetch(`/api/progress/${jobId}`);
            if (res.ok) {
              const pData = await res.json();
              if (pData && pData.status === 'processing') {
                this.animation.updateProgress(pData);
              }
            }
          } catch (e) {
            // ignore network jitter during poll
          }
          await new Promise(resolve => setTimeout(resolve, 250));
        }
      };

      pollProgress();

      try {
        const response = await fetch('/api/redact', {
          method: 'POST',
          body: formData
        });

        isProcessing = false;
        const data = await response.json();

        if (!response.ok) {
          const errorMsg = data.error || 'Server rejected the request.';
          this.setState(State.ERROR, { message: errorMsg });
          return;
        }

        // Successfully redacted
        this.setState(State.COMPLETED, { data: data });

      } catch (err) {
        isProcessing = false;
        this.setState(State.ERROR, {
          message: 'Network error or server unreachable. Please verify the backend is running.'
        });
      }
    }
  }

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', () => {
    window.redactProApp = new RedactProApp();
  });

})();

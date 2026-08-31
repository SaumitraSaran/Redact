/**
 * RedactPro — Upload & Drag-and-Drop Handler
 */

class UploadController {
  constructor(options) {
    this.dropzone = options.dropzone;
    this.fileInput = options.fileInput;
    this.dropzoneIdle = options.dropzoneIdle;
    this.fileCard = options.fileCard;
    this.fileNameDisplay = options.fileNameDisplay;
    this.fileSpecsDisplay = options.fileSpecsDisplay;
    this.fileBadge = options.fileBadge;
    this.removeBtn = options.removeBtn;
    this.onFileSelected = options.onFileSelected || (() => {});
    this.onFileRemoved = options.onFileRemoved || (() => {});

    this.selectedFile = null;
    this.supportedExtensions = ['.png', '.jpg', '.jpeg', '.pdf', '.mp4', '.mov'];

    this._bindEvents();
  }

  _bindEvents() {
    // Click dropzone to open file dialog
    this.dropzone.addEventListener('click', (e) => {
      if (e.target !== this.removeBtn && !this.removeBtn.contains(e.target)) {
        this.fileInput.click();
      }
    });

    // Keyboard accessibility (Enter or Space)
    this.dropzone.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        this.fileInput.click();
      }
    });

    // File input change
    this.fileInput.addEventListener('change', (e) => {
      const files = e.target.files;
      if (files && files.length > 0) {
        this.handleFile(files[0]);
      }
    });

    // Drag & Drop events
    ['dragenter', 'dragover'].forEach(eventName => {
      this.dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.dropzone.classList.add('drag-active');
      });
    });

    ['dragleave', 'drop'].forEach(eventName => {
      this.dropzone.addEventListener(eventName, (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.dropzone.classList.remove('drag-active');
      });
    });

    this.dropzone.addEventListener('drop', (e) => {
      const dt = e.dataTransfer;
      const files = dt.files;
      if (files && files.length > 0) {
        this.handleFile(files[0]);
      }
    });

    // Remove file button
    this.removeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      this.clearFile();
    });
  }

  handleFile(file) {
    if (!file) return;

    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!this.supportedExtensions.includes(ext)) {
      alert(`Unsupported file format "${ext}". Supported formats: PNG, JPG, PDF, MP4, MOV.`);
      return;
    }

    this.selectedFile = file;

    // Update UI
    this.dropzoneIdle.classList.add('hidden');
    this.fileCard.classList.remove('hidden');

    this.fileNameDisplay.textContent = file.name;
    this.fileBadge.textContent = ext.replace('.', '').toUpperCase();
    this.fileSpecsDisplay.textContent = `${ext.replace('.', '').toUpperCase()} · ${this.formatFileSize(file.size)}`;

    this.onFileSelected(file);
  }

  clearFile() {
    this.selectedFile = null;
    this.fileInput.value = '';

    this.fileCard.classList.add('hidden');
    this.dropzoneIdle.classList.remove('hidden');

    this.onFileRemoved();
  }

  getFile() {
    return this.selectedFile;
  }

  formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }
}

window.UploadController = UploadController;

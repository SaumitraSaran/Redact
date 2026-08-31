/**
 * RedactPro — Preview & Result Renderer
 */

class PreviewController {
  constructor(options) {
    this.mediaContainer = options.mediaContainer;
    this.chunksBar = options.chunksBar;
    this.chunksList = options.chunksList;
    this.downloadBtn = options.downloadBtn;
    this.metaStats = options.metaStats;

    this.currentData = null;
    this.activeChunkIndex = 0;
  }

  render(data) {
    this.currentData = data;
    this.activeChunkIndex = 0;
    this.mediaContainer.innerHTML = '';

    const results = data.results || [];
    if (results.length === 0) return;

    // Display statistics
    const meta = data.meta || {};
    if (data.file_type === 'image') {
      const count = meta.detections !== undefined ? meta.detections : 0;
      this.metaStats.textContent = `${count} sensitive item${count === 1 ? '' : 's'} permanently redacted.`;
    } else if (data.file_type === 'pdf') {
      const count = meta.total_detections !== undefined ? meta.total_detections : 0;
      const pages = meta.pages || 1;
      this.metaStats.textContent = `${count} item${count === 1 ? '' : 's'} redacted across ${pages} page${pages === 1 ? '' : 's'}. Text layer removed.`;
    } else if (data.file_type === 'video') {
      const count = meta.total_detections !== undefined ? meta.total_detections : 0;
      const chunks = meta.chunks || results.length;
      if (chunks > 1) {
        this.metaStats.textContent = `Video split into ${chunks} parts (10s limit). ${count} detections redacted.`;
      } else {
        this.metaStats.textContent = `${count} detections tracked and redacted throughout video.`;
      }
    }

    // Handle multi-chunk video selector
    if (results.length > 1) {
      this.chunksBar.classList.remove('hidden');
      this.chunksList.innerHTML = '';

      results.forEach((item, idx) => {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = `chunk-btn ${idx === 0 ? 'active' : ''}`;
        btn.textContent = `Part ${idx + 1}`;
        btn.addEventListener('click', () => {
          this.switchChunk(idx);
        });
        this.chunksList.appendChild(btn);
      });
    } else {
      this.chunksBar.classList.add('hidden');
    }

    // Display first or only result
    this.displayResultItem(results[0], data.file_type);
  }

  switchChunk(index) {
    if (!this.currentData || !this.currentData.results[index]) return;
    this.activeChunkIndex = index;

    // Update button active state
    const btns = this.chunksList.querySelectorAll('.chunk-btn');
    btns.forEach((b, idx) => {
      b.classList.toggle('active', idx === index);
    });

    this.displayResultItem(this.currentData.results[index], this.currentData.file_type);
  }

  displayResultItem(item, fileType) {
    this.mediaContainer.innerHTML = '';

    // Update download button
    this.downloadBtn.href = item.download_url;
    this.downloadBtn.setAttribute('download', item.filename);

    if (fileType === 'image') {
      const img = document.createElement('img');
      img.src = item.preview_url;
      img.alt = 'Redacted image preview';
      img.loading = 'lazy';
      this.mediaContainer.appendChild(img);
    } else if (fileType === 'video') {
      const video = document.createElement('video');
      video.controls = true;
      video.autoplay = false;
      video.playsInline = true;
      video.preload = 'metadata';
      video.style.maxWidth = '100%';
      video.style.maxHeight = '100%';
      video.style.backgroundColor = '#000000';

      const source = document.createElement('source');
      source.src = item.preview_url;
      source.type = 'video/mp4';
      video.appendChild(source);

      // Force load
      video.load();

      this.mediaContainer.appendChild(video);
    } else if (fileType === 'pdf') {
      const iframe = document.createElement('iframe');
      iframe.src = item.preview_url + '#toolbar=0&navpanes=0';
      iframe.title = 'Redacted PDF Preview';
      this.mediaContainer.appendChild(iframe);
    }
  }

  clear() {
    this.mediaContainer.innerHTML = '';
    this.chunksBar.classList.add('hidden');
    this.chunksList.innerHTML = '';
    this.currentData = null;
  }
}

window.PreviewController = PreviewController;

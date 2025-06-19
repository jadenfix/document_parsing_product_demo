// Enhanced Document Processing Platform JavaScript
document.addEventListener("DOMContentLoaded", () => {
  initializeApp();
});

function initializeApp() {
  setupDragAndDrop();
  setupFileInput();
  setupFormSubmission();
  setupProgressSteps();
  updateDocumentStats();
  
  // Initialize dynamic review section if data exists
  if (window.REVIEW_DATA) {
    renderReviewSection();
    updateProgressStep('review');
  }
}

function setupDragAndDrop() {
  const uploadZone = document.getElementById('upload-zone');
  const fileInput = document.getElementById('file-input');
  
  if (!uploadZone || !fileInput) return;
  
  // Prevent default drag behaviors
  ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    uploadZone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
  });
  
  // Highlight drop area when item is dragged over it
  ['dragenter', 'dragover'].forEach(eventName => {
    uploadZone.addEventListener(eventName, () => uploadZone.classList.add('dragover'), false);
  });
  
  ['dragleave', 'drop'].forEach(eventName => {
    uploadZone.addEventListener(eventName, () => uploadZone.classList.remove('dragover'), false);
  });
  
  // Handle dropped files
  uploadZone.addEventListener('drop', handleDrop, false);
  
  // Make entire upload zone clickable
  uploadZone.addEventListener('click', () => fileInput.click());
}

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function handleDrop(e) {
  const dt = e.dataTransfer;
  const files = dt.files;
  
  if (files.length > 0) {
    const file = files[0];
    if (file.type === 'application/pdf') {
      document.getElementById('file-input').files = files;
      showFileInfo(file);
    } else {
      showAlert('Please upload a PDF file.', 'warning');
    }
  }
}

function setupFileInput() {
  const fileInput = document.getElementById('file-input');
  if (!fileInput) return;
  
  fileInput.addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (file) {
      showFileInfo(file);
    }
  });
}

function showFileInfo(file) {
  const fileInfo = document.getElementById('file-info');
  const fileName = document.getElementById('file-name');
  const fileSize = document.getElementById('file-size');
  
  if (fileInfo && fileName && fileSize) {
    fileName.textContent = file.name;
    fileSize.textContent = formatFileSize(file.size);
    fileInfo.style.display = 'block';
  }
}

function formatFileSize(bytes) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

function setupFormSubmission() {
  const uploadForm = document.getElementById('upload-form');
  if (!uploadForm) return;
  
  uploadForm.addEventListener('submit', (e) => {
    e.preventDefault();
    
    const fileInput = document.getElementById('file-input');
    if (!fileInput.files[0]) {
      showAlert('Please select a PDF file to upload.', 'warning');
      return;
    }
    
    startProcessing();
    submitForm(uploadForm);
  });
}

function startProcessing() {
  // Hide upload section
  const uploadSection = document.getElementById('upload-section');
  if (uploadSection) {
    uploadSection.style.display = 'none';
  }
  
  // Show processing indicator
  const processing = document.getElementById('processing');
  if (processing) {
    processing.style.display = 'block';
  }
  
  // Update progress steps
  updateProgressStep('extract');
  
  // Simulate progress
  animateProgress();
}

function animateProgress() {
  const progressBar = document.getElementById('progress-bar');
  if (!progressBar) return;
  
  let progress = 0;
  const interval = setInterval(() => {
    progress += Math.random() * 10;
    if (progress > 95) progress = 95; // Don't complete until actual response
    
    progressBar.style.width = progress + '%';
    
    if (progress >= 95) {
      clearInterval(interval);
    }
  }, 200);
}

function submitForm(form) {
  const formData = new FormData(form);
  
  fetch(form.action, {
    method: 'POST',
    body: formData
  })
  .then(response => {
    if (response.redirected) {
      // Complete progress
      const progressBar = document.getElementById('progress-bar');
      if (progressBar) {
        progressBar.style.width = '100%';
      }
      
      // Redirect to review page
      setTimeout(() => {
        window.location.href = response.url;
      }, 500);
    } else {
      throw new Error('Upload failed');
    }
  })
  .catch(error => {
    console.error('Error:', error);
    showAlert('Upload failed. Please try again.', 'danger');
    resetToUpload();
  });
}

function resetToUpload() {
  const uploadSection = document.getElementById('upload-section');
  const processing = document.getElementById('processing');
  
  if (uploadSection) uploadSection.style.display = 'block';
  if (processing) processing.style.display = 'none';
  
  updateProgressStep('upload');
}

function setupProgressSteps() {
  // Determine current step based on page state
  if (window.REVIEW_DATA) {
    updateProgressStep('review');
  } else {
    updateProgressStep('upload');
  }
}

function updateProgressStep(currentStep) {
  const steps = ['upload', 'extract', 'match', 'review', 'export'];
  const currentIndex = steps.indexOf(currentStep);
  
  steps.forEach((step, index) => {
    const stepElement = document.getElementById(`step-${step}`);
    if (!stepElement) return;
    
    stepElement.classList.remove('active', 'complete');
    
    if (index < currentIndex) {
      stepElement.classList.add('complete');
    } else if (index === currentIndex) {
      stepElement.classList.add('active');
      stepElement.querySelector('.step-icon').classList.add('pulse');
    } else {
      stepElement.querySelector('.step-icon').classList.remove('pulse');
    }
  });
}

function renderReviewSection() {
  const data = window.REVIEW_DATA;
  if (!data) return;
  
  // Hide processing indicator if visible
  const processing = document.getElementById('processing');
  if (processing) {
    processing.style.display = 'none';
  }
  
  // If we already have server-rendered content, enhance it
  const existingReview = document.getElementById('review-section');
  if (existingReview) {
    enhanceReviewTable();
    return;
  }
  
  // Otherwise, create dynamic review section
  createDynamicReviewSection(data);
}

function enhanceReviewTable() {
  // Add confidence indicators and interactive features
  const selects = document.querySelectorAll('#review-section select');
  selects.forEach((select, index) => {
    updateConfidenceDisplay(select);
    select.addEventListener('change', () => updateConfidenceDisplay(select));
  });
}

function createDynamicReviewSection(data) {
  const container = document.getElementById('dynamic-review-section');
  if (!container) return;
  
  const reviewCard = document.createElement('div');
  reviewCard.className = 'review-card fade-in';
  reviewCard.innerHTML = generateReviewHTML(data);
  
  container.appendChild(reviewCard);
  enhanceReviewTable();
}

function generateReviewHTML(data) {
  return `
    <div class="review-header">
      <div class="row align-items-center">
        <div class="col">
          <h3 class="mb-0">
            <i class="fas fa-clipboard-check me-2"></i>
            Review & Confirm Matches
          </h3>
          <p class="mb-0 mt-2 opacity-75">
            Found ${data.rows.length} line items. Select the best catalog match for each item.
          </p>
        </div>
        <div class="col-auto">
          <div class="d-flex gap-2">
            <span class="confidence-badge confidence-high">
              <i class="fas fa-check me-1"></i>High Confidence
            </span>
            <span class="confidence-badge confidence-medium">
              <i class="fas fa-exclamation me-1"></i>Medium
            </span>
          </div>
        </div>
      </div>
    </div>
    
    <form method="POST" action="/confirm/${data.doc_id}" id="confirm-form">
      <div class="table-responsive">
        <table class="table table-hover mb-0">
          <thead class="table-light">
            <tr>
              <th style="width: 5%">#</th>
              <th style="width: 45%">
                <i class="fas fa-list me-2"></i>Extracted Description
              </th>
              <th style="width: 45%">
                <i class="fas fa-search me-2"></i>Catalog Match
              </th>
              <th style="width: 5%">
                <i class="fas fa-chart-line me-2"></i>Score
              </th>
            </tr>
          </thead>
          <tbody>
            ${data.rows.map((row, index) => `
              <tr class="match-row">
                <td class="align-middle">
                  <span class="badge bg-primary">${index + 1}</span>
                </td>
                <td class="align-middle">
                  <div class="fw-medium">${row.description}</div>
                </td>
                <td class="align-middle">
                  <select name="${row.match_id}" class="form-select">
                    ${row.choices.map((choice, choiceIndex) => `
                      <option value="${choiceIndex}" ${row.confirmed === choiceIndex ? 'selected' : ''}>
                        ${choice}
                      </option>
                    `).join('')}
                  </select>
                </td>
                <td class="align-middle text-center">
                  <span class="confidence-badge confidence-high" id="confidence-${row.match_id}">
                    <i class="fas fa-star me-1"></i>100%
                  </span>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
      
      <div class="p-4 bg-light">
        <div class="row align-items-center">
          <div class="col">
            <div class="d-flex align-items-center">
              <i class="fas fa-info-circle text-primary me-2"></i>
              <span class="text-muted">Review all matches before confirming. High-confidence matches are pre-selected.</span>
            </div>
          </div>
          <div class="col-auto">
            <button type="submit" class="btn btn-success-custom btn-lg">
              <i class="fas fa-download me-2"></i>
              Confirm & Export CSV
            </button>
          </div>
        </div>
      </div>
    </form>
  `;
}

function updateConfidence(select) {
  updateConfidenceDisplay(select);
}

function updateConfidenceDisplay(select) {
  const selectedIndex = select.selectedIndex;
  const confidenceElement = document.getElementById(`confidence-${select.name}`);
  
  if (!confidenceElement) return;
  
  // Calculate confidence based on selection position (first = highest)
  let confidence, confidenceClass, icon;
  
  if (selectedIndex === 0) {
    confidence = '100%';
    confidenceClass = 'confidence-high';
    icon = 'fas fa-star';
  } else if (selectedIndex === 1) {
    confidence = '95%';
    confidenceClass = 'confidence-high';
    icon = 'fas fa-star';
  } else if (selectedIndex === 2) {
    confidence = '85%';
    confidenceClass = 'confidence-medium';
    icon = 'fas fa-exclamation';
  } else {
    confidence = '70%';
    confidenceClass = 'confidence-medium';
    icon = 'fas fa-exclamation';
  }
  
  // Update confidence badge
  confidenceElement.className = `confidence-badge ${confidenceClass}`;
  confidenceElement.innerHTML = `<i class="${icon} me-1"></i>${confidence}`;
}

function updateDocumentStats() {
  // This could be enhanced to show real stats from the server
  const statsElement = document.getElementById('stats-processed');
  if (statsElement && window.REVIEW_DATA) {
    statsElement.textContent = '1'; // Or fetch from server
  }
}

function showAlert(message, type = 'info') {
  // Create a Bootstrap alert
  const alertDiv = document.createElement('div');
  alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
  alertDiv.innerHTML = `
    ${message}
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  `;
  
  // Insert at top of container
  const container = document.querySelector('.container');
  if (container) {
    container.insertBefore(alertDiv, container.firstChild);
    
    // Auto-dismiss after 5 seconds
    setTimeout(() => {
      if (alertDiv.parentNode) {
        alertDiv.remove();
      }
    }, 5000);
  }
} 
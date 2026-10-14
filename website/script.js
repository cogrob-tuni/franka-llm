const copyButton = document.getElementById('copy');
const citation = document.getElementById('citation');
const status = document.getElementById('copy-status');

copyButton.addEventListener('click', async () => {
  const text = citation.textContent.trim();
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const helper = document.createElement('textarea');
      helper.value = text;
      helper.setAttribute('readonly', '');
      helper.style.position = 'fixed';
      helper.style.opacity = '0';
      document.body.appendChild(helper);
      helper.select();
      document.execCommand('copy');
      helper.remove();
    }
    copyButton.textContent = 'Copied';
    status.textContent = 'Citation copied to clipboard.';
  } catch {
    status.textContent = 'Copy failed. Select the citation text to copy it manually.';
  }
  window.setTimeout(() => { copyButton.textContent = 'Copy citation'; }, 1800);
});

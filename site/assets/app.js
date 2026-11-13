"use strict";

const copyButton = document.getElementById("copy-all");
const noticeText = document.getElementById("notice-text");
const copyStatus = document.getElementById("copy-status");
const copyLabel = copyButton?.querySelector("span");

function getNoticeValue() {
  const lines = noticeText.querySelectorAll(".line-content");
  if (lines.length) {
    return Array.from(lines, (line) => line.textContent || "").join("\n");
  }
  return noticeText.textContent || "";
}

function legacyCopy(value) {
  const temporary = document.createElement("textarea");
  temporary.value = value;
  temporary.setAttribute("aria-hidden", "true");
  temporary.setAttribute("autocomplete", "off");
  temporary.style.position = "fixed";
  temporary.style.top = "0";
  temporary.style.left = "-9999px";
  temporary.style.width = "1px";
  temporary.style.height = "1px";
  temporary.style.opacity = "0";
  temporary.contentEditable = "true";
  temporary.readOnly = false;
  document.body.appendChild(temporary);

  try {
    temporary.focus({ preventScroll: true });
  } catch (_) {
    temporary.focus();
  }
  temporary.select();
  temporary.setSelectionRange(0, value.length);

  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch (_) {
    copied = false;
  }
  temporary.remove();
  return copied;
}

async function copyNotice() {
  const value = getNoticeValue();
  let copied = legacyCopy(value);

  if (!copied && window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      copied = true;
    } catch (_) {
      copied = false;
    }
  }

  if (!copied) {
    const selection = window.getSelection();
    if (selection) {
      const range = document.createRange();
      range.selectNodeContents(noticeText);
      selection.removeAllRanges();
      selection.addRange(range);
    }
  }

  const original = copyLabel?.textContent || copyButton.textContent;
  const resultText = copied ? copyButton.dataset.success : copyButton.dataset.failure;
  if (copyLabel) {
    copyLabel.textContent = resultText;
  } else {
    copyButton.textContent = resultText;
  }
  copyStatus.textContent = resultText;

  window.setTimeout(() => {
    if (copyLabel) {
      copyLabel.textContent = original;
    } else {
      copyButton.textContent = original;
    }
    copyStatus.textContent = "";
  }, 2200);
}

if (copyButton && noticeText && copyStatus) {
  copyButton.addEventListener("click", copyNotice);
}

const noticeSearch = document.getElementById("notice-search");
const noticeCount = document.getElementById("notice-count");
const searchEmpty = document.getElementById("notice-search-empty");

if (noticeSearch && noticeCount && searchEmpty) {
  const normalize = (value) => value.normalize("NFKC").toLowerCase().trim();
  const rows = Array.from(document.querySelectorAll(".notice-list__row"), (row) => ({
    element: row,
    text: normalize([
      row.querySelector(".notice-list__title").textContent,
      row.querySelector(".notice-list__number").textContent,
      row.dataset.noticeId,
    ].join(" ")),
  }));

  noticeSearch.parentElement.hidden = rows.length === 0;
  noticeSearch.addEventListener("input", () => {
    const query = normalize(noticeSearch.value);
    const terms = query.split(/\s+/);
    let matches = 0;
    for (const { element, text } of rows) {
      const visible = terms.every((term) => text.includes(term));
      element.hidden = !visible;
      if (visible) matches++;
    }
    searchEmpty.hidden = matches !== 0;
    noticeCount.textContent = query ? "검색 결과 " + matches + "건" : "총 " + rows.length + "건";
  });
}

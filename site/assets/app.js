"use strict";

const copyButton = document.getElementById("copy-all");
const noticeText = document.getElementById("notice-text");

async function copyNotice() {
  const value = noticeText.textContent;
  try {
    await navigator.clipboard.writeText(value);
  } catch (_) {
    const temporary = document.createElement("textarea");
    temporary.value = value;
    temporary.setAttribute("readonly", "");
    temporary.style.position = "fixed";
    temporary.style.opacity = "0";
    document.body.appendChild(temporary);
    temporary.select();
    document.execCommand("copy");
    temporary.remove();
  }

  const korean = document.documentElement.lang === "ko";
  const original = korean ? "전체 내용 복사하기" : "Copy all text";
  copyButton.textContent = korean ? "복사 완료" : "Copied";
  window.setTimeout(() => {
    copyButton.textContent = original;
  }, 1600);
}

copyButton.addEventListener("click", copyNotice);

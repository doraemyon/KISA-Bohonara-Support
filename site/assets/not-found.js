"use strict";

const route = window.location.pathname.match(
  /^\/KISA-Bohonara-Support\/notices\/(\d{1,20})\/(ko|en)\/?$/,
);
const title = document.getElementById("page-title");
const description = document.getElementById("page-description");
const retryButton = document.getElementById("retry-button");
const sourceLink = document.getElementById("source-link");
const checkStatus = document.getElementById("check-status");

if (route) {
  const [, noticeId, language] = route;
  const english = language === "en";
  document.documentElement.lang = english ? "en" : "ko";
  document.title = english
    ? "Preparing notice · KISA Notice"
    : "공지 문서 준비 중 · KISA Notice";
  title.textContent = english ? "Preparing the notice" : "공지 문서를 준비하고 있습니다";
  description.textContent = english
    ? "This page will open automatically as soon as the Korean and English documents are published."
    : "국문·영문 문서 게시가 완료되면 이 페이지에서 자동으로 공지를 엽니다.";
  retryButton.textContent = english ? "Check again" : "다시 확인";
  retryButton.hidden = false;
  sourceLink.textContent = english ? "KISA source" : "KISA 원문";
  sourceLink.href =
    "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&menuNo=205020&nttId=" +
    encodeURIComponent(noticeId);

  let checking = false;
  let timer;

  async function checkPage() {
    if (checking) return;
    checking = true;
    retryButton.disabled = true;
    checkStatus.textContent = english ? "Checking publication status…" : "게시 상태를 확인하고 있습니다…";
    try {
      const separator = window.location.search ? "&" : "?";
      const response = await fetch(
        `${window.location.pathname}${window.location.search}${separator}check=${Date.now()}`,
        { cache: "no-store" },
      );
      if (response.ok) {
        window.location.replace(`${window.location.pathname}?published=${Date.now()}`);
        return;
      }
      checkStatus.textContent = english
        ? "The document is still being prepared. This page checks again automatically."
        : "아직 문서를 생성하는 중입니다. 잠시 후 자동으로 다시 확인합니다.";
    } catch (_) {
      checkStatus.textContent = english
        ? "Could not check the page. Retrying shortly."
        : "페이지 상태를 확인하지 못했습니다. 잠시 후 다시 시도합니다.";
    } finally {
      checking = false;
      retryButton.disabled = false;
      window.clearTimeout(timer);
      timer = window.setTimeout(checkPage, 5000);
    }
  }

  retryButton.addEventListener("click", checkPage);
  timer = window.setTimeout(checkPage, 1200);
}

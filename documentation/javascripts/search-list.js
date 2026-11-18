// The list of the search results (issue 654). Material makes it a stop of the Tab key (tabindex="0"), so that a long
// list scrolls by the keyboard. Empty, it has no height on a wide screen, and the focus vanishes there. It stays out
// of the Tab key until it holds a result; its text, the count of the results, stays read either way.
(() => {
  const list = document.querySelector(".md-search__scrollwrap");
  if (!list) return;
  const sync = () => {
    list.setAttribute("tabindex", list.querySelector(".md-search-result__item") ? "0" : "-1");
  };
  sync();
  new MutationObserver(sync).observe(list, { childList: true, subtree: true });
})();

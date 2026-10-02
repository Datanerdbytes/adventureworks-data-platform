// Native details provides keyboard activation; dismiss on selection or Escape.
document.addEventListener("change", (event) => {
  const menu = event.target.closest(".chart-type-menu");
  if (menu) {
    menu.open = false;
    menu.querySelector("summary").focus();
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  document.querySelectorAll(".chart-type-menu[open]").forEach((menu) => {
    menu.open = false;
    menu.querySelector("summary").focus();
  });
});
document.addEventListener("click", (event) => {
  document.querySelectorAll(".chart-type-menu[open]").forEach((menu) => {
    if (!menu.contains(event.target)) menu.open = false;
  });
});

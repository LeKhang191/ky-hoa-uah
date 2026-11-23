const gallery = document.querySelector("[data-masonry]");

if (gallery && "ResizeObserver" in window) {
  const cards = gallery.querySelectorAll(".gallery-card > a");
  gallery.classList.add("is-masonry");
  const rowHeight = parseFloat(getComputedStyle(gallery).gridAutoRows);
  const resizeCard = (card) => {
    const rows = Math.ceil(card.getBoundingClientRect().height / rowHeight);
    card.parentElement.style.gridRowEnd = `span ${rows}`;
  };
  cards.forEach(resizeCard);

  const observer = new ResizeObserver((entries) => {
    for (const { target } of entries) resizeCard(target);
  });
  cards.forEach((card) => observer.observe(card, { box: "border-box" }));
}

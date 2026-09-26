const list = document.querySelector("#case-list");
const detail = document.querySelector("#case-detail");
const count = document.querySelector("#case-count");

const escapeText = (value) => String(value ?? "");

function statusClass(status) {
  return `status status-${String(status).toLowerCase().replaceAll(" ", "-")}`;
}

async function loadCases() {
  try {
    const response = await fetch("/api/cases", { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    const data = await response.json();
    count.textContent = data.count;
    list.replaceChildren();

    for (const record of data.cases) {
      const button = document.createElement("button");
      button.className = "case-row";
      button.dataset.caseId = record.id;

      const main = document.createElement("span");
      main.className = "case-main";
      const title = document.createElement("strong");
      title.textContent = record.title;
      const meta = document.createElement("small");
      meta.textContent = `LL-${record.id} · ${record.category} · ${record.created_at}`;
      main.append(title, meta);

      const badge = document.createElement("span");
      badge.className = statusClass(record.status);
      badge.textContent = record.status;
      button.append(main, badge);
      button.addEventListener("click", () => loadCase(record.id, button));
      list.append(button);
    }
  } catch (error) {
    list.innerHTML = '<div class="alert">Unable to load assigned records.</div>';
  }
}

async function loadCase(caseId, selectedButton) {
  document.querySelectorAll(".case-row").forEach((row) => row.classList.remove("selected"));
  selectedButton?.classList.add("selected");
  detail.innerHTML = '<div class="loading">Loading record…</div>';

  try {
    // The application requests a single record by its numeric object identifier.
    const response = await fetch(`/api/cases/${caseId}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error(`Request failed: ${response.status}`);
    const { case: record } = await response.json();

    detail.replaceChildren();
    const header = document.createElement("div");
    header.className = "detail-heading";
    const ref = document.createElement("span");
    ref.className = "eyebrow";
    ref.textContent = `RECORD LL-${record.id}`;
    const title = document.createElement("h2");
    title.textContent = escapeText(record.title);
    const badge = document.createElement("span");
    badge.className = statusClass(record.status);
    badge.textContent = record.status;
    header.append(ref, title, badge);

    const grid = document.createElement("dl");
    grid.className = "metadata";
    for (const [label, value] of [
      ["Owner", record.owner], ["Category", record.category],
      ["Priority", record.priority], ["Created", record.created_at]
    ]) {
      const wrapper = document.createElement("div");
      const dt = document.createElement("dt");
      const dd = document.createElement("dd");
      dt.textContent = label;
      dd.textContent = escapeText(value);
      wrapper.append(dt, dd);
      grid.append(wrapper);
    }

    const summary = section("Summary", record.summary);
    const notes = section("Internal notes", record.internal_notes, "notes");
    detail.append(header, grid, summary, notes);
  } catch (error) {
    detail.innerHTML = '<div class="alert">Unable to load that record.</div>';
  }
}

function section(title, text, className = "") {
  const sectionElement = document.createElement("section");
  sectionElement.className = `record-section ${className}`.trim();
  const heading = document.createElement("h3");
  const paragraph = document.createElement("p");
  heading.textContent = title;
  paragraph.textContent = escapeText(text);
  sectionElement.append(heading, paragraph);
  return sectionElement;
}

loadCases();

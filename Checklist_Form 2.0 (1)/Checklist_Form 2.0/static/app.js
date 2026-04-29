async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  let data = {};
  try {
    data = await response.json();
  } catch (_) {}
  if (!response.ok) {
    throw new Error(data.error || data.message || `Request failed: ${url}`);
  }
  return data;
}

function $(selector, root = document) {
  return root.querySelector(selector);
}

function $all(selector, root = document) {
  return [...root.querySelectorAll(selector)];
}

function showMessage(target, message, type = "success") {
  if (!target) return;
  target.className = `notice notice-${type}`;
  target.textContent = message;
  target.classList.remove("hidden");
}

document.addEventListener("DOMContentLoaded", () => {
  setupLoginPage();
  setupRegisterPage();
  setupOperatorPage();
  setupSupervisorPage();
  setupChecklistFormPage();
});

function setupLoginPage() {
  const form = document.getElementById("loginForm");
  if (!form) return;

  form.addEventListener("submit", function (e) {
    e.preventDefault();

    const employeeId = document.getElementById("employee_id")?.value.trim();
    const password = document.getElementById("password")?.value.trim();
    const messageBox = document.getElementById("loginMessage");

    if (!employeeId || !password) {
      if (messageBox) {
        messageBox.className = "notice notice-error";
        messageBox.textContent = "Please enter Employee ID and Password.";
        messageBox.classList.remove("hidden");
      }
      return;
    }

    const id = employeeId.toLowerCase();

    if (id.startsWith("adm")) {
      window.location.href = "/admin";
    } else if (id.startsWith("sup")) {
      window.location.href = "/supervisor";
    } else {
      window.location.href = "/operator";
    }
  });
}

function setupRegisterPage() {
  const form = $("#registerForm");
  if (!form) return;

  const roleSelect = $("#role");
  const checklistSection = $("#checklistAssignmentSection");
  const messageBox = $("#registerMessage");

  function toggleChecklistSection() {
    if (!roleSelect || !checklistSection) return;
    checklistSection.classList.toggle("hidden", roleSelect.value !== "Operator");
  }

  roleSelect?.addEventListener("change", toggleChecklistSection);
  toggleChecklistSection();

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    showMessage(messageBox, "Registered successfully. You can now sign in.", "success");
    setTimeout(() => {
      window.location.href = "/login";
    }, 900);
  });
}

function setupOperatorPage() {
  const mount = $("#operatorChecklistMount");
  if (!mount) return;

  fetchJson("/api/checklists")
    .then((items) => {
      if (!Array.isArray(items) || !items.length) {
        mount.innerHTML = `<div class="card"><p class="muted">No assigned checklists found.</p></div>`;
        return;
      }

      const grouped = {};
      items.forEach((item) => {
        const category = item.category || "General Checklist";
        if (!grouped[category]) grouped[category] = [];
        grouped[category].push(item);
      });

      mount.innerHTML = Object.entries(grouped).map(([category, entries]) => `
        <section class="category-block">
          <p class="eyebrow">Category</p>
          <h2 class="category-title">${category}</h2>
          <div class="card-grid">
            ${entries.map(item => `
              <article class="checklist-card">
                <span class="status-pill status-pending">Assigned</span>
                <h3>${item.title || item.name || item.slug}</h3>
                <div class="checklist-meta">
                  <div><strong>Slug:</strong> ${item.slug}</div>
                  <div><strong>Category:</strong> ${item.category || "-"}</div>
                  <div><strong>Description:</strong> ${item.description || "Checklist ready to fill"}</div>
                </div>
                <div class="card-actions">
                  <a class="btn btn-primary" href="/forms/${item.slug}">Open Form</a>
                </div>
              </article>
            `).join("")}
          </div>
        </section>
      `).join("");
    })
    .catch((err) => {
      mount.innerHTML = `<div class="card"><p class="notice notice-error">${err.message}</p></div>`;
    });
}

function setupSupervisorPage() {
  const tableBody = $("#pendingTableBody");
  if (!tableBody) return;

  fetchJson("/api/supervisor/pending")
    .then((rows) => {
      if (!rows.length) {
        tableBody.innerHTML = `<tr><td colspan="7">No pending submissions found.</td></tr>`;
        return;
      }

      tableBody.innerHTML = rows.map(row => `
        <tr>
          <td>${row.batch}</td>
          <td>${row.sequence}</td>
          <td>${row.slug}</td>
          <td>${row.shift}</td>
          <td>${row.operator}</td>
          <td>${row.time}</td>
          <td class="card-actions">
            <button class="btn btn-secondary btn-preview" data-batch="${row.batch}" data-slug="${row.slug}">Preview</button>
            <button class="btn btn-success btn-approve" data-batch="${row.batch}" data-seq="${row.sequence}" data-slug="${row.slug}">Approve</button>
          </td>
        </tr>
      `).join("");

      bindSupervisorActions();
    })
    .catch((err) => {
      tableBody.innerHTML = `<tr><td colspan="7">${err.message}</td></tr>`;
    });
}

function bindSupervisorActions() {
  $all(".btn-preview").forEach((button) => {
    button.addEventListener("click", async () => {
      const batch = button.dataset.batch;
      const slug = button.dataset.slug;
      const previewMount = $("#previewMount");
      if (!previewMount) return;

      previewMount.innerHTML = `<div class="card"><p class="muted">Loading preview...</p></div>`;
      try {
        const data = await fetchJson(`/api/supervisor/preview/${batch}/${slug}`);
        previewMount.innerHTML = `
          <div class="table-wrap">
            <table>
              <tbody>
                ${data.rows.slice(0, 20).map(row => `
                  <tr>
                    <td><strong>${row.index}</strong></td>
                    <td>${row.cells.join(" | ")}</td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `;
      } catch (err) {
        previewMount.innerHTML = `<div class="notice notice-error">${err.message}</div>`;
      }
    });
  });

  $all(".btn-approve").forEach((button) => {
    button.addEventListener("click", async () => {
      try {
        const payload = {
          batch_id: button.dataset.batch,
          sequence: button.dataset.seq,
          slug: button.dataset.slug,
          approver: "Supervisor"
        };
        const result = await fetchJson("/api/checklists/approve", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        alert(result.message || "Approved");
        window.location.reload();
      } catch (err) {
        alert(err.message);
      }
    });
  });
}

function createInput(field, value = "") {
  if (field.input_type === "select") {
    const select = document.createElement("select");
    select.name = field.id;
    select.required = !!field.required;
    const options = field.options || ["", "OK", "NOT OK"];
    options.forEach((optionValue) => {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = optionValue || "Select...";
      if (optionValue === value) option.selected = true;
      select.appendChild(option);
    });
    return select;
  }

  if (field.input_type === "textarea") {
    const textarea = document.createElement("textarea");
    textarea.name = field.id;
    textarea.value = value || "";
    textarea.required = !!field.required;
    return textarea;
  }

  const input = document.createElement("input");
  input.name = field.id;
  input.type = field.input_type || "text";
  input.required = !!field.required;
  input.value = value || "";
  if (field.answer_type === "Hours") {
    input.step = "0.01";
    input.min = "0";
  }
  return input;
}

function buildSheetFieldTable(title, fields, initialValues, groupName) {
  const panel = document.createElement("section");
  panel.className = "panel";

  const heading = document.createElement("h2");
  heading.className = "section-title";
  heading.textContent = title;
  panel.appendChild(heading);

  const wrap = document.createElement("div");
  wrap.className = "sheet-table-wrap";

  const table = document.createElement("table");
  table.className = "sheet-table sheet-table-fields";

  const tbody = document.createElement("tbody");

  for (let index = 0; index < fields.length; index += 2) {
    const row = document.createElement("tr");
    const pair = fields.slice(index, index + 2);

    pair.forEach((field) => {
      const labelCell = document.createElement("th");
      labelCell.textContent = field.label;

      const valueCell = document.createElement("td");
      const input = createInput(field, initialValues[field.id] || "");
      input.id = `${groupName}_${field.id}`;
      input.dataset.group = groupName;
      input.dataset.fieldId = field.id;
      input.classList.add("sheet-input");
      valueCell.appendChild(input);

      row.appendChild(labelCell);
      row.appendChild(valueCell);
    });

    if (pair.length === 1) {
      row.innerHTML += `<th></th><td></td>`;
    }

    tbody.appendChild(row);
  }

  table.appendChild(tbody);
  wrap.appendChild(table);
  panel.appendChild(wrap);
  return panel;
}

function buildSectionTable(section, initialValues) {
  const wrapper = document.createElement("div");
  wrapper.className = "sheet-table-wrap";

  const table = document.createElement("table");
  table.className = "sheet-table";

  const thead = document.createElement("thead");
  thead.innerHTML = `
    <tr>
      <th>Sr. No.</th>
      <th>Item</th>
      <th>Check Point</th>
      <th>Reference</th>
      <th>Answer</th>
    </tr>
  `;
  table.appendChild(thead);

  const tbody = document.createElement("tbody");

  section.items.forEach((item, index) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td>${item.serial_no || index + 1}</td>
      <td>${item.item || "-"}</td>
      <td>${item.label || item.question || "-"}</td>
      <td>${item.reference || "-"}</td>
      <td></td>
    `;

    const answerCell = row.lastElementChild;
    const input = createInput(item, initialValues[item.id] || "");
    input.dataset.group = section.title;
    input.dataset.fieldId = item.id;
    input.classList.add("sheet-input");
    answerCell.appendChild(input);

    tbody.appendChild(row);
  });

  table.appendChild(tbody);
  wrapper.appendChild(table);
  return wrapper;
}

function collectFormPayload(schema, mount) {
  const payload = {
    metadata: {},
    sections: [],
    summary: {}
  };

  mount.querySelectorAll("[data-group='metadata']").forEach((input) => {
    payload.metadata[input.dataset.fieldId] = input.value;
  });

  mount.querySelectorAll("[data-group='summary']").forEach((input) => {
    payload.summary[input.dataset.fieldId] = input.value;
  });

  schema.sections.forEach((section) => {
    const items = [];
    mount.querySelectorAll(`[data-group="${CSS.escape(section.title)}"]`).forEach((input) => {
      items.push({
        id: input.dataset.fieldId,
        value: input.value
      });
    });
    payload.sections.push({
      title: section.title,
      items
    });
  });

  return payload;
}

function setupChecklistFormPage() {
  const mount = $("#checklistMount");
  if (!mount) return;

  const slug = mount.dataset.slug;
  if (!slug) return;

  Promise.all([
    fetchJson(`/api/checklists/${slug}`),
    fetchJson(`/api/templates/${slug}`)
  ])
    .then(([schema, template]) => {
      renderChecklistForm(mount, slug, schema, template);
    })
    .catch((err) => {
      mount.innerHTML = `<div class="notice notice-error">${err.message}</div>`;
    });
}

function renderChecklistForm(mount, slug, schema, template) {
  mount.innerHTML = "";

  const header = document.createElement("section");
  header.className = "panel form-page-header";
  header.innerHTML = `
    <p class="eyebrow">Checklist Workspace</p>
    <h1>${schema.title || slug}</h1>
    <p class="muted">Source: ${schema.source_workbook || "Workbook not specified"}</p>
  `;
  mount.appendChild(header);

  mount.appendChild(
    buildSheetFieldTable(
      "Machine & Shift Details",
      schema.metadata_fields || [],
      template.metadata || {},
      "metadata"
    )
  );

  (schema.sections || []).forEach((section) => {
    const panel = document.createElement("section");
    panel.className = "panel";

    const title = document.createElement("h2");
    title.className = "section-title";
    title.textContent = section.title;
    panel.appendChild(title);

    const templateSection = (template.sections || []).find((s) => s.title === section.title);
    const initialValues = Object.fromEntries((templateSection?.items || []).map((item) => [item.id, item.value]));

    if (section.items && section.items.length > 0) {
      panel.appendChild(buildSectionTable(section, initialValues));
    } else {
      const p = document.createElement("p");
      p.className = "muted";
      p.textContent = "No checklist items in this section.";
      panel.appendChild(p);
    }

    mount.appendChild(panel);
  });

  mount.appendChild(
    buildSheetFieldTable(
      "Verification & Sign-off",
      schema.closing_fields || [],
      template.summary || {},
      "summary"
    )
  );

  const actionPanel = document.createElement("section");
  actionPanel.className = "panel";
  actionPanel.innerHTML = `
    <div class="actions">
      <button id="submitChecklistBtn" class="btn btn-primary">Submit Checklist</button>
      <a href="/operator" class="btn btn-secondary">Back to Operator Dashboard</a>
      <div id="formMessage" class="notice hidden"></div>
    </div>
  `;
  mount.appendChild(actionPanel);

  $("#submitChecklistBtn")?.addEventListener("click", async () => {
    const messageBox = $("#formMessage");
    try {
      const payload = collectFormPayload(schema, mount);
      const result = await fetchJson(`/api/checklists/${slug}/save`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify(payload)
      });
      showMessage(messageBox, result.message || "Checklist saved successfully.", "success");
    } catch (err) {
      showMessage(messageBox, err.message, "error");
    }
  });
}
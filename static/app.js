document.addEventListener("DOMContentLoaded", () => {
  const data = window.REVIEW_DATA;
  const wrapper = document.getElementById("review-section");
  if (!data || !wrapper || wrapper.childElementCount > 0) return; // already rendered

  // Build a form dynamically so the user can confirm matches
  const form = document.createElement("form");
  form.method = "POST";
  form.action = `/confirm/${data.doc_id}`;
  form.classList.add("mt-4");

  const table = document.createElement("table");
  table.classList.add("table", "table-striped");
  table.innerHTML = "<tr><th>Description</th><th>Your Match</th></tr>";

  data.rows.forEach((r) => {
    const opts = r.choices
      .map(
        (c, i) =>
          `<option value=\"${i}\" ${r.confirmed === i ? "selected" : ""}>${c}</option>`
      )
      .join("");

    table.innerHTML += `
      <tr>
        <td>${r.description}</td>
        <td><select name="${r.match_id}" class="form-select">${opts}</select></td>
      </tr>`;
  });

  form.appendChild(table);
  form.innerHTML +=
    '<button class="btn btn-success">Confirm &amp; Download CSV</button>';
  wrapper.appendChild(form);
}); 
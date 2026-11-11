// small helpers for the whole web UI (no framework needed)

const loader = document.getElementById("loader");

function showLoader(text) {
    document.getElementById("loader-text").textContent = text || "Loading…";
    loader.hidden = false;
}

// forms and links with data-loading show the overlay while the server works
document.querySelectorAll("form[data-loading]").forEach(form => {
    form.addEventListener("submit", () => {
        showLoader(form.dataset.loading);
        // disable the buttons only after the browser has read the form,
        // otherwise the value of the clicked button (e.g. correct=yes) is not sent
        setTimeout(() => form.querySelectorAll("button").forEach(button => button.disabled = true), 0);
    });
});
document.querySelectorAll("a[data-loading]").forEach(link => {
    link.addEventListener("click", () => showLoader(link.dataset.loading));
});
// the browser "back" button can restore a page with the overlay still open
window.addEventListener("pageshow", () => {
    loader.hidden = true;
    document.querySelectorAll("form button").forEach(button => button.disabled = false);
});

// messages: close button, success messages disappear after a few seconds
document.querySelectorAll(".alert[role=status]").forEach(alert => {
    alert.querySelector(".alert-close").addEventListener("click", () => alert.remove());
    if (alert.classList.contains("alert-success")) {
        setTimeout(() => alert.classList.add("fade"), 5000);
        setTimeout(() => alert.remove(), 5500);
    }
});

// sidebar on small screens
const sidebar = document.getElementById("sidebar");
document.getElementById("menu-toggle").addEventListener("click", () => sidebar.classList.toggle("open"));
document.getElementById("sidebar-backdrop").addEventListener("click", () => sidebar.classList.remove("open"));

// small button spinner for actions that call the API without reloading the page
async function withSpinner(button, work) {
    const label = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '<span class="spinner small"></span> ' + (button.dataset.busy || "Working…");
    try {
        await work();
    } finally {
        button.disabled = false;
        button.innerHTML = label;
    }
}

async function postJson(url, data) {
    const response = await fetch(url, {
        method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(data),
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.error || "Something went wrong");
    return body;
}

// ---------- scan page: drag & drop, preview, checks before upload ----------
const dropZone = document.getElementById("drop-zone");
if (dropZone) {
    const input = document.getElementById("image");
    const preview = document.getElementById("preview");
    const info = document.getElementById("file-info");
    const submit = document.getElementById("scan-submit");
    const MAX_MB = 5;

    function choose(file) {
        info.className = "file-info";
        if (!file) return;
        if (!["image/jpeg", "image/png"].includes(file.type)) {
            info.textContent = file.name + " is not a JPEG or PNG photo.";
            info.classList.add("error");
            submit.disabled = true;
            return;
        }
        if (file.size > MAX_MB * 1024 * 1024) {
            info.textContent = "The photo is " + (file.size / 1048576).toFixed(1) + " MB, the limit is " + MAX_MB + " MB.";
            info.classList.add("error");
            submit.disabled = true;
            return;
        }
        preview.src = URL.createObjectURL(file);
        dropZone.classList.add("has-image");
        info.textContent = file.name + " · " + (file.size / 1024).toFixed(0) + " KB";
        submit.disabled = false;
    }

    input.addEventListener("change", () => choose(input.files[0]));
    ["dragenter", "dragover"].forEach(name => dropZone.addEventListener(name, event => {
        event.preventDefault();
        dropZone.classList.add("dragging");
    }));
    ["dragleave", "drop"].forEach(name => dropZone.addEventListener(name, event => {
        event.preventDefault();
        dropZone.classList.remove("dragging");
    }));
    dropZone.addEventListener("drop", event => {
        if (event.dataTransfer.files.length) {
            input.files = event.dataTransfer.files;
            choose(input.files[0]);
        }
    });
}

// ---------- sorting guide: search + ask the coach ----------
const search = document.getElementById("rule-search");
if (search) {
    const cards = [...document.querySelectorAll(".rule")];
    const empty = document.getElementById("no-rules");
    let category = "all";

    function filter() {
        const text = search.value.trim().toLowerCase();
        let shown = 0;
        cards.forEach(card => {
            const match = card.dataset.search.includes(text) && (category === "all" || card.dataset.category === category);
            card.hidden = !match;
            if (match) shown++;
        });
        empty.hidden = shown > 0;
    }
    search.addEventListener("input", filter);
    document.querySelectorAll(".filter").forEach(chip => chip.addEventListener("click", () => {
        document.querySelectorAll(".filter").forEach(c => c.classList.remove("active"));
        chip.classList.add("active");
        category = chip.dataset.category;
        filter();
    }));
}

const askForm = document.getElementById("ask-form");
if (askForm) {
    const answer = document.getElementById("answer");
    askForm.addEventListener("submit", event => {
        event.preventDefault();
        const button = askForm.querySelector("button");
        withSpinner(button, async () => {
            answer.hidden = false;
            answer.className = "answer";
            try {
                const body = await postJson("/api/coach/ask", {question: askForm.question.value});
                answer.innerHTML = "";
                const text = document.createElement("p");
                text.textContent = body.text;
                const source = document.createElement("p");
                source.className = "source";
                source.textContent = "Source: " + body.source;
                answer.append(text, source);
            } catch (error) {
                answer.className = "answer error";
                answer.textContent = error.message;
            }
        });
    });
    document.querySelectorAll(".example-question").forEach(example => example.addEventListener("click", () => {
        askForm.question.value = example.textContent;
        askForm.requestSubmit();
    }));
}

// ---------- dashboard: AI insights ----------
const insightsButton = document.getElementById("insights-button");
if (insightsButton) {
    insightsButton.addEventListener("click", () => withSpinner(insightsButton, async () => {
        const box = document.getElementById("insights");
        const response = await fetch(insightsButton.dataset.url);
        const body = await response.json();
        box.hidden = false;
        box.innerHTML = "";
        if (!response.ok) {
            box.textContent = body.error || "Could not create insights";
            return;
        }
        const list = document.createElement("ul");
        body.text.split("\n").filter(line => line.trim()).forEach(line => {
            const item = document.createElement("li");
            item.textContent = line.replace(/^\s*[-•*]\s*/, "");
            list.append(item);
        });
        const source = document.createElement("p");
        source.className = "source";
        source.textContent = "Source: " + body.source;
        box.append(list, source);
    }));
}

// ---------- address form: city from a list, street and house number from EDG ----------
document.querySelectorAll("[data-address]").forEach(box => {
    const region = box.querySelector("[data-region]");
    const row = box.querySelector("[data-street-row]");
    const street = box.querySelector("[data-street]");
    const list = box.querySelector("datalist");
    const number = box.querySelector("[data-number]");
    const hint = box.querySelector("[data-address-hint]");
    const defaultHint = hint.textContent;
    let streets = [];
    let timer = null;

    function setHint(text, error) {
        hint.textContent = text || defaultHint;
        hint.classList.toggle("error", Boolean(error));
    }

    async function getJson(url) {
        const response = await fetch(url);
        const body = await response.json();
        if (!response.ok) throw new Error(body.error || "EDG is not reachable");
        return body;
    }

    async function loadNumbers(selected) {
        number.innerHTML = '<option value="">–</option>';
        if (!streets.includes(street.value)) return;
        number.disabled = true;
        try {
            (await getJson("/api/address/numbers?street=" + encodeURIComponent(street.value))).forEach(n => {
                const option = new Option(n, n, false, n === selected);
                number.add(option);
            });
            setHint();
        } catch (error) {
            setHint(error.message, true);
        }
        number.disabled = false;
    }

    async function loadStreets() {
        const text = street.value.trim();
        if (!text) return;
        try {
            streets = await getJson("/api/address/streets?q=" + encodeURIComponent(text));
            list.innerHTML = "";
            streets.forEach(s => list.append(new Option(s)));
            if (!streets.length) setHint("No Dortmund street starts with “" + text + "”.", true);
            else setHint();
        } catch (error) {
            setHint(error.message, true);
        }
    }

    function showStreetFields() {
        const dortmund = region.value === "Dortmund";
        row.hidden = !dortmund;
        if (!dortmund) {
            street.value = "";
            number.innerHTML = '<option value="">–</option>';
            setHint("Collection days are only available for Dortmund, so no address is needed.");
        } else {
            setHint();
        }
    }

    region.addEventListener("change", showStreetFields);
    street.addEventListener("input", () => {
        clearTimeout(timer);
        timer = setTimeout(async () => {
            await loadStreets();
            if (streets.includes(street.value)) loadNumbers("");
        }, 250);
    });
    street.addEventListener("change", () => loadNumbers(""));

    showStreetFields();
    if (street.value) {
        // a saved address: show its house numbers with the saved one selected
        loadStreets().then(() => loadNumbers(number.dataset.value));
    }
});

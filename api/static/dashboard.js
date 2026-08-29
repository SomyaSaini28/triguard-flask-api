(() => {
  const form = document.querySelector("#prediction-form");
  const submitButton = document.querySelector("#submit-button");
  const connection = document.querySelector("#connection-status");
  const modelVersion = document.querySelector("#model-version");
  const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
  const emptyResult = document.querySelector("#empty-result");
  const resultContent = document.querySelector("#result-content");
  const outputState = document.querySelector("#output-state");
  const resultHeading = document.querySelector("#result-heading");

  const sampleCase = {
    case_id: "JAIPUR-2408", medicine_name: "Insulin", medicine_criticality: "5",
    cold_chain_required: "true", supplier_id: "S2", destination_facility: "District Hospital Jaipur",
    supplier_on_time_rate: "0.68", supplier_fill_rate: "0.72", lead_time_days: "8",
    lead_time_variability: "4.5", route_delay_days: "3.8", weather_risk_score: "8",
    demand_spike_factor: "1.40", current_stock_days: "3", warehouse_utilization: "88"
  };

  function setConnection(state, message) {
    connection.className = `connection ${state ? `is-${state}` : ""}`;
    connection.lastChild.textContent = ` ${message}`;
  }

  async function checkHealth() {
    try {
      const response = await fetch("/health", { headers: { Accept: "application/json" } });
      const health = await response.json();
      if (!response.ok || !health.model_loaded) throw new Error("Model unavailable");
      setConnection("ready", "Service ready");
      modelVersion.textContent = health.model_version || "Risk model ready";
    } catch (_) {
      setConnection("error", "Service unavailable");
      modelVersion.textContent = "Model unavailable";
    }
  }

  function setOutputState(label, type = "") {
    outputState.textContent = label;
    outputState.className = `output-state ${type ? `is-${type}` : ""}`;
  }

  function numericValue(formData, name) { return Number(formData.get(name)); }

  function buildPayload() {
    const data = new FormData(form);
    return {
      case_id: data.get("case_id").trim() || null,
      medicine_name: data.get("medicine_name").trim(),
      medicine_criticality: numericValue(data, "medicine_criticality"),
      cold_chain_required: data.get("cold_chain_required") === "true",
      supplier_id: data.get("supplier_id").trim(),
      destination_facility: data.get("destination_facility").trim(),
      supplier_on_time_rate: numericValue(data, "supplier_on_time_rate"),
      supplier_fill_rate: numericValue(data, "supplier_fill_rate"),
      lead_time_days: numericValue(data, "lead_time_days"),
      lead_time_variability: numericValue(data, "lead_time_variability"),
      route_delay_days: numericValue(data, "route_delay_days"),
      weather_risk_score: numericValue(data, "weather_risk_score"),
      demand_spike_factor: numericValue(data, "demand_spike_factor"),
      current_stock_days: numericValue(data, "current_stock_days"),
      warehouse_utilization: numericValue(data, "warehouse_utilization")
    };
  }

  function riskTheme(band) {
    const themes = {
      low: ["#17a388", "LOW RISK"], moderate: ["#d38b20", "MODERATE RISK"],
      high: ["#dc6834", "HIGH RISK"], critical: ["#d4484a", "CRITICAL RISK"]
    };
    return themes[band.toLowerCase()] || ["#6b7280", band];
  }

  function renderResult(result) {
    const [color, label] = riskTheme(result.risk_band);
    const risk = Math.round(result.risk_probability * 100);
    document.querySelector("#risk-gauge").style.cssText = `position: relative; --risk: ${risk}; --risk-color: ${color};`;
    document.querySelector("#risk-value").textContent = `${risk}%`;
    const riskBand = document.querySelector("#risk-band");
    riskBand.textContent = label;
    riskBand.style.color = color;
    riskBand.style.backgroundColor = `${color}18`;
    document.querySelector("#triage-action").textContent = result.triage_action;
    document.querySelector("#response-sla").textContent = `Response target: ${result.response_sla}`;
    document.querySelector("#result-model").textContent = result.model_version;
    document.querySelector("#review-status").textContent = result.review_required ? "Human review required" : "Standard review";
    document.querySelector("#result-case").textContent = result.case_id || "Unassigned";
    document.querySelector("#action-list").replaceChildren(...result.recommended_actions.map(action => {
      const item = document.createElement("li"); item.textContent = action; return item;
    }));
    document.querySelector("#signal-list").replaceChildren(...result.operational_signals.map(signal => {
      const item = document.createElement("article"); item.className = "signal"; item.dataset.direction = signal.direction;
      const title = document.createElement("strong"); title.textContent = signal.name;
      const detail = document.createElement("span"); detail.textContent = signal.detail;
      item.append(title, detail); return item;
    }));
    const qualitySection = document.querySelector("#quality-section");
    qualitySection.hidden = !result.data_quality_flags.length;
    document.querySelector("#quality-list").replaceChildren(...result.data_quality_flags.map(flag => {
      const item = document.createElement("li"); item.textContent = flag; return item;
    }));
    document.querySelector("#result-request").textContent = `Assessment ID: ${result.request_id}`;
    resultHeading.textContent = "Assessment complete";
    setOutputState("Live result", "live");
    emptyResult.hidden = true;
    resultContent.hidden = false;
  }

  function showError(message) {
    resultHeading.textContent = "Assessment needs attention";
    setOutputState("Action needed", "error");
    emptyResult.hidden = false;
    emptyResult.querySelector("h3").textContent = "We could not complete the assessment.";
    emptyResult.querySelector("p").textContent = message;
    resultContent.hidden = true;
  }

  function clearInvalidFields() { form.querySelectorAll(".is-invalid").forEach(field => field.classList.remove("is-invalid")); }

  form.addEventListener("input", event => { if (event.target.matches("input")) event.target.classList.remove("is-invalid"); });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    clearInvalidFields();
    if (!form.checkValidity()) {
      [...form.querySelectorAll(":invalid")].forEach(field => field.classList.add("is-invalid"));
      form.reportValidity();
      return;
    }
    submitButton.disabled = true;
    submitButton.classList.add("is-loading");
    setOutputState("Assessing", "");
    try {
      const response = await fetch("/dashboard/predictions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken, "X-Request-ID": `dashboard-${Date.now()}` },
        body: JSON.stringify(buildPayload())
      });
      const body = await response.json();
      if (!response.ok) {
        if (response.status === 401) { throw new Error("Your session has ended. Refresh the page and sign in again."); }
        const detail = body.error?.details?.[0]?.msg;
        throw new Error(detail || body.error?.message || "The server could not score this case.");
      }
      renderResult(body);
    } catch (error) {
      showError(error.message || "Check that the Flask server is running, then try again.");
    } finally {
      submitButton.disabled = false;
      submitButton.classList.remove("is-loading");
    }
  });

  document.querySelector("#load-sample").addEventListener("click", () => {
    Object.entries(sampleCase).forEach(([name, value]) => {
      const element = form.elements.namedItem(name);
      if (element instanceof RadioNodeList) element.value = value;
      else if (element) element.value = value;
    });
    clearInvalidFields();
  });

  checkHealth();
})();

"use strict";

document.querySelectorAll("[data-flash-message]").forEach((message) => {
    const dismiss = () => {
        message.classList.add("is-dismissing");
        window.setTimeout(() => message.remove(), 200);
    };
    const dismissButton = message.querySelector(".flash-dismiss");

    dismissButton?.addEventListener("click", dismiss);
    window.setTimeout(dismiss, message.classList.contains("flash-error") ? 8000 : 5000);
});

const recoveryForm = document.querySelector("[data-supabase-recovery]");

if (recoveryForm) {
    const recoveryParams = new URLSearchParams(window.location.hash.slice(1));
    const accessToken = recoveryParams.get("access_token");
    const refreshToken = recoveryParams.get("refresh_token");
    const isRecovery = recoveryParams.get("type") === "recovery";
    const status = recoveryForm.querySelector("[data-recovery-status]");
    const submit = recoveryForm.querySelector('button[type="submit"]');

    if (accessToken && refreshToken && isRecovery) {
        recoveryForm.querySelector("[data-recovery-access-token]").value = accessToken;
        recoveryForm.querySelector("[data-recovery-refresh-token]").value = refreshToken;
        submit.disabled = false;
        status.textContent = "Recovery link verified. Choose a new password.";
        window.history.replaceState(null, "", window.location.pathname);
    } else {
        status.textContent = "This recovery link is invalid or expired. Request a new reset link.";
    }
}

const briefBuilder = document.querySelector("[data-brief-builder]");

if (briefBuilder) {
    const fields = {
        title: briefBuilder.querySelector("[data-preview-title]"),
        description: briefBuilder.querySelector("[data-preview-description]"),
        category: briefBuilder.querySelector('[name="category"]'),
        budget: briefBuilder.querySelector('[name="budget"]'),
        format: briefBuilder.querySelector('[name="aspect_ratio"]'),
        usage: briefBuilder.querySelector('[name="commercial_use"]'),
        duration: briefBuilder.querySelector('[name="usage_duration"]'),
        territory: briefBuilder.querySelector('[name="territory"]'),
    };

    const outputs = {
        title: document.querySelector("[data-preview-title-output]"),
        description: document.querySelector("[data-preview-description-output]"),
        category: document.querySelector("[data-preview-category]"),
        budget: document.querySelector("[data-preview-budget]"),
        format: document.querySelector("[data-preview-format]"),
        usage: document.querySelector("[data-preview-usage]"),
    };

    const updatePreview = () => {
        outputs.title.textContent = fields.title.value.trim() || "Your project title";
        outputs.description.textContent =
            fields.description.value.trim() || "Your idea will take shape here as you write.";
        outputs.category.textContent = fields.category.value || "Any";
        const budget = Number(fields.budget.value);
        outputs.budget.textContent = `₹${Number.isFinite(budget) ? budget.toLocaleString("en-IN") : "0"}`;
        outputs.format.textContent = fields.format.value.trim() || "Not set";
        outputs.usage.textContent = [
            fields.usage.value.trim() || "Usage not set",
            fields.duration.value.trim() || "Duration not set",
        ].join(" · ");
    };

    Object.values(fields).forEach((field) => {
        field.addEventListener("input", updatePreview);
        field.addEventListener("change", updatePreview);
    });
    updatePreview();
}

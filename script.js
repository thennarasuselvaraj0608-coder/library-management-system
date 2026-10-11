/**
 * Automated Library Book Tracking and Management System
 * Client-Side JavaScript
 */

document.addEventListener("DOMContentLoaded", function () {
    // -------------------------------------------------------------------------
    // 1. Mobile Sidebar Toggle & Overlay
    // -------------------------------------------------------------------------
    const sidebar = document.getElementById("sidebar");
    const toggleBtn = document.getElementById("sidebarToggleBtn");
    const overlay = document.getElementById("sidebarOverlay");

    if (toggleBtn && sidebar) {
        toggleBtn.addEventListener("click", function () {
            sidebar.classList.toggle("show");
            if (overlay) overlay.classList.toggle("show");
        });
    }

    if (overlay) {
        overlay.addEventListener("click", function () {
            sidebar.classList.remove("show");
            overlay.classList.remove("show");
        });
    }

    // -------------------------------------------------------------------------
    // 2. Auto-dismiss Flash Alerts
    // -------------------------------------------------------------------------
    const alerts = document.querySelectorAll(".alert-dismissible");
    alerts.forEach(function (alert) {
        setTimeout(function () {
            try {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            } catch (e) {
                // If bootstrap not loaded yet
            }
        }, 6000);
    });

    // -------------------------------------------------------------------------
    // 3. Client-side Quick Table Search (for instant filtering)
    // -------------------------------------------------------------------------
    const liveSearchInput = document.getElementById("tableLiveSearch");
    const targetTable = document.querySelector(".table-searchable");

    if (liveSearchInput && targetTable) {
        liveSearchInput.addEventListener("keyup", function () {
            const query = this.value.toLowerCase().trim();
            const rows = targetTable.querySelectorAll("tbody tr");

            rows.forEach(function (row) {
                const text = row.textContent.toLowerCase();
                if (text.includes(query)) {
                    row.style.display = "";
                } else {
                    row.style.display = "none";
                }
            });
        });
    }

    // -------------------------------------------------------------------------
    // 4. Return Book Modal Population
    // -------------------------------------------------------------------------
    const returnModal = document.getElementById("returnBookModal");
    if (returnModal) {
        returnModal.addEventListener("show.bs.modal", function (event) {
            const button = event.relatedTarget;
            if (!button) return;

            const issueId = button.getAttribute("data-issue-id");
            const bookTitle = button.getAttribute("data-book-title");
            const studentName = button.getAttribute("data-student-name");
            const regNo = button.getAttribute("data-reg-no");
            const dueDate = button.getAttribute("data-due-date");
            const overdueDays = parseInt(button.getAttribute("data-overdue-days") || "0", 10);
            const calculatedFine = parseFloat(button.getAttribute("data-fine") || "0.00");

            const form = document.getElementById("returnBookForm");
            form.action = `/return/${issueId}`;

            document.getElementById("modalBookTitle").textContent = bookTitle || "-";
            document.getElementById("modalStudent").textContent = `${studentName} (${regNo})`;
            document.getElementById("modalDueDate").textContent = dueDate || "-";

            const overdueBadge = document.getElementById("modalOverdueBadge");
            const fineSection = document.getElementById("modalFineSection");
            const fineAmountText = document.getElementById("modalFineAmount");

            if (overdueDays > 0) {
                overdueBadge.innerHTML = `<span class="badge bg-danger">${overdueDays} Days Overdue</span>`;
                fineSection.style.display = "block";
                fineAmountText.textContent = `₹${calculatedFine.toFixed(2)}`;
            } else {
                overdueBadge.innerHTML = `<span class="badge bg-success">On Time</span>`;
                fineSection.style.display = "none";
                fineAmountText.textContent = "₹0.00";
            }
        });
    }

    // -------------------------------------------------------------------------
    // 5. Issue Date to Due Date Auto Calculator (Defaults to +14 Days)
    // -------------------------------------------------------------------------
    const issueDateInput = document.getElementById("issue_date");
    const dueDateInput = document.getElementById("due_date");

    if (issueDateInput && dueDateInput) {
        issueDateInput.addEventListener("change", function () {
            if (this.value) {
                const issueDate = new Date(this.value);
                if (!isNaN(issueDate.getTime())) {
                    issueDate.setDate(issueDate.getDate() + 14);
                    const yyyy = issueDate.getFullYear();
                    const mm = String(issueDate.getMonth() + 1).padStart(2, "0");
                    const dd = String(issueDate.getDate()).padStart(2, "0");
                    dueDateInput.value = `${yyyy}-${mm}-${dd}`;
                }
            }
        });
    }

    // -------------------------------------------------------------------------
    // 6. Chart.js Initializer (Dashboard)
    // -------------------------------------------------------------------------
    initDashboardCharts();
});

function initDashboardCharts() {
    const catCanvas = document.getElementById("categoryChart");
    const deptCanvas = document.getElementById("departmentChart");

    if (!catCanvas && !deptCanvas) return;

    // Fetch API data or read inline data attributes
    fetch("/api/chart-data")
        .then((response) => response.json())
        .then((data) => {
            if (data.status !== "success") return;

            // 1. Categories Chart (Doughnut)
            if (catCanvas && typeof Chart !== "undefined") {
                new Chart(catCanvas, {
                    type: "doughnut",
                    data: {
                        labels: data.categories,
                        datasets: [
                            {
                                data: data.category_copies,
                                backgroundColor: [
                                    "#2563eb",
                                    "#3b82f6",
                                    "#60a5fa",
                                    "#93c5fd",
                                    "#0ea5e9",
                                    "#06b6d4",
                                    "#14b8a6",
                                ],
                                borderWidth: 2,
                                borderColor: "#ffffff",
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: {
                                position: "bottom",
                                labels: {
                                    boxWidth: 12,
                                    font: { size: 11 },
                                },
                            },
                        },
                        cutout: "68%",
                    },
                });
            }

            // 2. Department Chart (Bar)
            if (deptCanvas && typeof Chart !== "undefined") {
                new Chart(deptCanvas, {
                    type: "bar",
                    data: {
                        labels: data.departments,
                        datasets: [
                            {
                                label: "Total Book Issues",
                                data: data.department_issues,
                                backgroundColor: "#2563eb",
                                borderRadius: 6,
                            },
                        ],
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                            legend: { display: false },
                        },
                        scales: {
                            y: {
                                beginAtZero: true,
                                ticks: { precision: 0 },
                                grid: { color: "#f1f5f9" },
                            },
                            x: {
                                grid: { display: false },
                            },
                        },
                    },
                });
            }
        })
        .catch((err) => console.log("Chart loading skipped:", err));
}

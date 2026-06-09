const form = document.getElementById("uploadForm")
const jobsList = document.getElementById("jobsList")
const logPanel = document.getElementById("logPanel")
const logEntries = document.getElementById("logEntries")
const clearLogsBtn = document.getElementById("clearLogs")

const apiBaseUrl = window.location.protocol === "file:" || window.location.origin === "null"
    ? "http://localhost:8000"
    : ""
const jobs = []

// Logs 

function log(level, message) {
    const levels = { info: "INFO", warn: "WARN", error: "ERROR" }
    const now = new Date().toLocaleTimeString("es-AR", { hour12: false })
 
    const entry = document.createElement("div")
    entry.className = `log-entry log-${level}`
    entry.innerHTML = `<span class="log-time">${now}</span><span class="log-level">${levels[level]}</span><span class="log-msg">${message}</span>`
    logEntries.appendChild(entry)
 
    // Scroll al ultimo log
    logEntries.scrollTop = logEntries.scrollHeight
}
 
clearLogsBtn.addEventListener("click", () => {
    logEntries.innerHTML = ""
    log("info", "Logs limpiados")
})



function formatJobStatus(status) {
    return status || "queued"
}

function renderJobs() {
    jobsList.innerHTML = ""

    if (jobs.length === 0) {
        const emptyState = document.createElement("p")
        emptyState.className = "empty-state"
        emptyState.textContent = "Todavía no hay trabajos enviados."
        jobsList.appendChild(emptyState)
        return
    }

    jobs.forEach(job => {
        const div = document.createElement("div")
        div.className = "job"
        const downloadLink = job.status === "completed"
            ? `<a class="download-link" href="${apiBaseUrl}/api/jobs/${job.id}/download">Descargar</a>`
            : ""
        div.innerHTML = `
            <div class="job-info">
                <span class="job-name">${job.name}</span>
                <span class="job-details">${job.resolution}p • ${job.samples} samples</span>
            </div>
            <span class="status ${job.status}">${formatJobStatus(job.status)}</span>
            ${downloadLink}
        `
        jobsList.appendChild(div)
    })
}

async function loadJobs() {
    try {
        const response = await fetch(
            `${apiBaseUrl}/api/jobs?t=${Date.now()}`,
            { cache: "no-store" })       
        if (!response.ok) {
            throw new Error("No se pudieron cargar los trabajos")
        }

        const data = await response.json()
        const prev = jobs.map(j => j.status)
        jobs.splice(0, jobs.length, ...(data.jobs || []))
        jobs.forEach((job, i) => {
            if (prev[i] !== undefined && prev[i] !== job.status) {
                log("info", `Job "${job.name}" cambió de estado: ${prev[i]} → ${job.status}`)
            }
        })
 
        renderJobs()
    } catch (error) {
        log("error", `Error al cargar trabajos: ${error.message}`)
        renderJobs()
    }
}

form.addEventListener("submit", async event => {
    event.preventDefault()

    const fileInput = document.getElementById("sceneFile")
    const file = fileInput.files[0]

    if (!file) {
        return
    }

    const resolution = document.getElementById("resolution").value
    const samples = document.getElementById("samples").value
    const jobName = document.getElementById("jobName").value || file.name
 
    log("info", `Enviando "${jobName}" — ${file.name} (${(file.size / 1024 / 1024).toFixed(2)} MB, ${resolution}p, ${samples} samples)`)


    const submitButton = form.querySelector("button[type='submit']")
    submitButton.disabled = true
    submitButton.textContent = "Enviando..."

    try {
        const formData = new FormData()
        formData.append("sceneFile", file)
        formData.append("resolution", document.getElementById("resolution").value)
        formData.append("samples", document.getElementById("samples").value)
        formData.append("jobName", document.getElementById("jobName").value)

        const response = await fetch(`${apiBaseUrl}/api/renders`, {
            method: "POST",
            body: formData
        })

        const payload = await response.json()

        if (!response.ok) {
            throw new Error(payload.error || "No se pudo encolar el trabajo")
        }

        log("info", `Job encolado con id ${payload.job.id}`)
        await loadJobs()
        form.reset()
    } catch (error) {
        log("error", `Error al enviar render: ${error.message}`)
        alert(error.message)
    } finally {
        submitButton.disabled = false
        submitButton.textContent = "Enviar Render"
    }
})

log("info", "Aplicación iniciada")
loadJobs()

const REFRESH_INTERVAL = 5000

setInterval(loadJobs, REFRESH_INTERVAL)
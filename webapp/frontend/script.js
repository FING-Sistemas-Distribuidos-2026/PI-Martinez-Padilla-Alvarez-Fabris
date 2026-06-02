const form = document.getElementById("uploadForm")
const jobsList = document.getElementById("jobsList")

const apiBaseUrl = window.location.protocol === "file:" || window.location.origin === "null"
    ? "http://localhost:8000"
    : ""
const jobs = []

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
        const response = await fetch(`${apiBaseUrl}/api/jobs`)
        if (!response.ok) {
            throw new Error("No se pudieron cargar los trabajos")
        }

        const data = await response.json()
        jobs.splice(0, jobs.length, ...(data.jobs || []))
        renderJobs()
    } catch (error) {
        console.error(error)
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

        jobs.unshift(payload.job)
        renderJobs()
        form.reset()
    } catch (error) {
        console.error(error)
        alert(error.message)
    } finally {
        submitButton.disabled = false
        submitButton.textContent = "Enviar Render"
    }
})

loadJobs()
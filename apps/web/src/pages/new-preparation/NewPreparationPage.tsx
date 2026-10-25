import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { createPreparation } from "../../api";
import { ArrowLeft, BriefcaseBusiness, Check, Search } from "lucide-react";
import "./NewPreparationPage.css";

const presets = [
  {
    title: "Backend Engineer",
    category: "Engineering",
    description:
      "Design and build REST services in Python. Own data models, review code and improve reliability of production systems.",
  },
  {
    title: "Frontend Developer",
    category: "Engineering",
    description:
      "Build accessible, responsive web applications using JavaScript, TypeScript, React, HTML and CSS. Write tests and collaborate with designers and backend engineers.",
  },
  {
    title: "QA Automation Engineer",
    category: "Engineering",
    description:
      "Design and execute manual and automated tests. Use Playwright, TypeScript, API testing, CI/CD pipelines and bug tracking tools to improve software quality.",
  },
  {
    title: "Data Analyst",
    category: "Data",
    description:
      "Analyze datasets, write SQL queries, create dashboards, identify trends and communicate actionable insights using data visualization tools.",
  },
  {
    title: "Product Manager",
    category: "Product",
    description:
      "Define product requirements, prioritize roadmaps, analyze user feedback and collaborate with engineering, design and business teams.",
  },
];

const categories = ["All", "Engineering", "Data", "Product"];

export default function NewPreparationPage() {
  const navigate = useNavigate();

  const [search, setSearch] = useState("");
  const [category, setCategory] = useState("All");
  const [jobTitle, setJobTitle] = useState("");
  const [description, setDescription] = useState("");
  const [resume, setResume] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  const filteredPresets = presets.filter((preset) => {
    const matchesCategory =
      category === "All" || preset.category === category;
    const matchesSearch =
      `${preset.title} ${preset.category} ${preset.description}`
        .toLowerCase()
        .includes(search.toLowerCase());

    return matchesCategory && matchesSearch;
  });

  function selectPreset(preset: (typeof presets)[number]) {
    setJobTitle(preset.title);
    setDescription(preset.description);
    setError("");
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (saving) return;

    if (!jobTitle.trim() || !description.trim()) {
      setError("Please enter a job title and job description.");
      return;
    }

    setSaving(true);
    setError("");

    try {
      const preparation = await createPreparation({
        job_title: jobTitle.trim(),
        job_description: description.trim(),
        resume: resume.trim() || null,
      });

      navigate(`/preparations/${preparation.id}`);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not save your preparation. Please try again.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="page-content new-preparation-page">
      <button
        type="button"
        className="new-prep-back"
        onClick={() => navigate(-1)}
      >
        <ArrowLeft size={17} />
        Back
      </button>

      <header className="new-prep-heading">
        <p className="eyebrow">GET READY FOR YOUR NEXT OPPORTUNITY</p>
        <h1>New preparation</h1>
        <p>Start from a preset or paste your own job description.</p>
      </header>

      <section className="new-prep-panel preset-panel">
        <div className="new-prep-section-title">
          <BriefcaseBusiness size={19} />
          <h2>Start from a preset</h2>
        </div>

        <label className="new-prep-search">
          <Search size={19} />
          <input
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            placeholder="Search presets"
            aria-label="Search presets"
          />
        </label>

        <div className="preset-filters" aria-label="Preset categories">
          {categories.map((item) => (
            <button
              type="button"
              key={item}
              className={`preset-filter ${category === item ? "active" : ""}`}
              onClick={() => setCategory(item)}
            >
              {item}
            </button>
          ))}
        </div>

        <div className="preset-grid">
          {filteredPresets.map((preset) => {
            const selected = jobTitle === preset.title;

            return (
              <button
                type="button"
                key={preset.title}
                className={`preset-card ${selected ? "selected" : ""}`}
                onClick={() => selectPreset(preset)}
                aria-pressed={selected}
              >
                <span className="preset-card-top">
                  <strong>{preset.title}</strong>
                  {selected && <Check size={18} />}
                </span>
                <span className="preset-category">{preset.category}</span>
              </button>
            );
          })}

          {filteredPresets.length === 0 && (
            <p className="preset-empty">No matching presets found.</p>
          )}
        </div>
      </section>

      <form className="new-prep-panel new-prep-form" onSubmit={handleSubmit}>
        <div className="new-prep-field">
          <div className="new-prep-label-row">
            <label htmlFor="job-title">Job title</label>
            <span>{jobTitle.length} / 120</span>
          </div>
          <input
            id="job-title"
            value={jobTitle}
            onChange={(event) => setJobTitle(event.target.value)}
            maxLength={120}
            placeholder="e.g. QA Automation Engineer"
            required
          />
        </div>

        <div className="new-prep-field">
          <div className="new-prep-label-row">
            <label htmlFor="job-description">Job description</label>
            <span>{description.length.toLocaleString()} / 20,000</span>
          </div>
          <textarea
            id="job-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            maxLength={20000}
            rows={6}
            placeholder="Paste the job description here..."
            required
          />
        </div>

        <div className="new-prep-field">
          <div className="new-prep-label-row">
            <label htmlFor="resume">Resume (optional)</label>
            <span>{resume.length.toLocaleString()} / 20,000</span>
          </div>
          <textarea
            id="resume"
            value={resume}
            onChange={(event) => setResume(event.target.value)}
            maxLength={20000}
            rows={4}
            placeholder="Paste your resume text. File upload is not available yet."
          />
          <p className="new-prep-help">
            Your resume text can help tailor interview practice to your
            experience.
          </p>
        </div>

        {error && (
          <p className="new-prep-message" role="alert">
            {error}
          </p>
        )}

        <div className="new-prep-actions">
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate(-1)}
          >
            Cancel
          </button>
          <button type="submit" className="btn btn-primary">
            Create preparation
          </button>
        </div>
      </form>
    </div>
  );
}

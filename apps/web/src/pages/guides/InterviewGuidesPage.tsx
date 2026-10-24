import {
  BookOpen,
  BriefcaseBusiness,
  Code2,
  MessageCircle,
  Search,
} from "lucide-react";
import { useState } from "react";
import "./InterviewGuidesPage.css";
const guides = [
  {
    title: "Tell me about yourself",
    category: "Communication",
    icon: MessageCircle,
    desc: "Build a concise introduction that connects your experience to the role.",
  },
  {
    title: "Behavioral questions",
    category: "Communication",
    icon: BriefcaseBusiness,
    desc: "Use the STAR method to tell clear stories about your work.",
  },
  {
    title: "Technical interview basics",
    category: "Technical",
    icon: Code2,
    desc: "Practice explaining your reasoning and breaking down a problem.",
  },
  {
    title: "Questions to ask an interviewer",
    category: "Preparation",
    icon: BookOpen,
    desc: "Prepare thoughtful questions about the team, role, and expectations.",
  },
];
export default function InterviewGuidesPage() {
  const [search, setSearch] = useState("");
  const shown = guides.filter((g) =>
    `${g.title} ${g.category} ${g.desc}`
      .toLowerCase()
      .includes(search.toLowerCase()),
  );
  return (
    <div className="page-content guides-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">LEARN & PRACTICE</p>
          <h1>Interview guides</h1>
          <p>Simple, practical resources to help you feel ready.</p>
        </div>
      </div>
      <label className="guide-search">
        <Search size={18} />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search interview topics..."
        />
      </label>
      <div className="guide-grid">
        {shown.map(({ title, category, icon: Icon, desc }) => (
          <article className="card guide-card" key={title}>
            <span className="guide-icon">
              <Icon size={21} />
            </span>
            <span className="pill">{category}</span>
            <h2>{title}</h2>
            <p>{desc}</p>
            <button
              className="btn btn-secondary"
              onClick={() =>
                window.alert(`Guide content for “${title}” can be added here.`)
              }
            >
              Explore guide <span>↗</span>
            </button>
          </article>
        ))}
      </div>
      {shown.length === 0 && (
        <div className="card empty-guides">
          No guides match “{search}”. Try another keyword.
        </div>
      )}
    </div>
  );
}

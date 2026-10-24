import {
  ArrowUpRight,
  Award,
  ChartNoAxesColumnIncreasing,
  Target,
} from "lucide-react";
import "./ProgressPage.css";
export default function ProgressPage() {
  return (
    <div className="page-content progress-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">YOUR GROWTH</p>
          <h1>My progress</h1>
          <p>See the work you're putting in and the skills you're building.</p>
        </div>
        <span className="pill">Personal overview</span>
      </div>
      <div className="grid grid-3">
        <div className="card progress-metric">
          <span className="metric-icon">
            <ChartNoAxesColumnIncreasing />
          </span>
          <small>Sessions completed</small>
          <strong>04</strong>
          <span className="metric-foot">Keep your streak going</span>
        </div>
        <div className="card progress-metric">
          <span className="metric-icon mint">
            <Target />
          </span>
          <small>Questions practiced</small>
          <strong>28</strong>
          <span className="metric-foot">Practice builds confidence</span>
        </div>
        <div className="card progress-metric">
          <span className="metric-icon peach">
            <Award />
          </span>
          <small>Practice time</small>
          <strong>1.5h</strong>
          <span className="metric-foot">Every minute counts</span>
        </div>
      </div>
      <section className="card progress-panel">
        <div>
          <h2>Skill development</h2>
          <p className="muted">
            A sample view of the skills you're practicing. Update this with
            report data when your API is connected.
          </p>
        </div>
        {[
          ["Communication", 72],
          ["Problem solving", 58],
          ["Technical knowledge", 64],
          ["Confidence", 48],
        ].map(([name, value]) => (
          <div className="skill-row" key={name as string}>
            <div>
              <span>{name}</span>
              <strong>{value}%</strong>
            </div>
            <div className="progress-track">
              <span style={{ width: `${value}%` }} />
            </div>
          </div>
        ))}
      </section>
      <div className="progress-next">
        <span>
          <ArrowUpRight />
        </span>
        <div>
          <strong>Your next step</strong>
          <p>
            Complete another practice interview and review the feedback to see
            where you're improving.
          </p>
        </div>
      </div>
    </div>
  );
}

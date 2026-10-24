import { ArrowRight, Target } from 'lucide-react';
import { Link } from 'react-router-dom';
type Props = { id: string; title: string; level: string; progress: number; questions: number };
export default function PreparationCard({ id, title, level, progress, questions }: Props) { return <article className="prep-card card"><span className="prep-symbol violet"><Target size={22}/></span><span className="pill">{level}</span><h3>{title}</h3><div className="prep-meta"><span>{questions} questions</span><span>{progress}% complete</span></div><div className="progress-track"><span style={{ width: `${progress}%` }}/></div><Link className="btn btn-secondary prep-action" to={`/preparations/${id}`}>Continue <ArrowRight size={15}/></Link></article>; }

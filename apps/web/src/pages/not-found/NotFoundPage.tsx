import { Link } from "react-router-dom";

export default function NotFoundPage() {
  return (
    <div>
      <h1>This item could not be found</h1>
      <Link to="/">Go home</Link>
    </div>
  );
}

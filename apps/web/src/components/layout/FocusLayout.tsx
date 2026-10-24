import { Link, Outlet } from "react-router-dom";

/** No navigation, only a Leave link, so nothing distracts from answering. */
export default function FocusLayout() {
  return (
    <div>
      <header>
        <Link to="/">Leave</Link>
      </header>
      <main>
        <Outlet />
      </main>
    </div>
  );
}

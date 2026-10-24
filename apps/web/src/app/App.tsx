import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "../components/layout/AppLayout";
import DashboardPage from "../pages/dashboard/DashboardPage";
import ProgressPage from "../pages/progress/ProgressPage";
import InterviewGuidesPage from "../pages/guides/InterviewGuidesPage";
import SettingsPage from "../pages/settings/SettingsPage";
import PreparationHubPage from "../pages/preparation/PreparationHubPage";
import InterviewRoomPage from "../pages/interview/InterviewRoomPage";
import GradingPage from "../pages/grading/GradingPage";
import ReportPage from "../pages/report/ReportPage";
import "./App.css";

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<DashboardPage />} />
        <Route path="progress" element={<ProgressPage />} />
        <Route path="guides" element={<InterviewGuidesPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route
          path="preparations/:preparationId"
          element={<PreparationHubPage />}
        />
        <Route path="interview/:sessionId" element={<InterviewRoomPage />} />
        <Route path="grading/:sessionId" element={<GradingPage />} />
        <Route path="reports/:reportId" element={<ReportPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

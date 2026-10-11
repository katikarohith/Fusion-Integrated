import { lazy } from "react";
import { Navigate, type RouteObject } from "react-router-dom";

const ApplyPage = lazy(() => import("./pages/ApplyPage"));
const MyLeavePage = lazy(() => import("./pages/MyLeavePage"));
const BalancesPage = lazy(() => import("./pages/BalancesPage"));
const TasksPage = lazy(() => import("./pages/TasksPage"));
const AdminPage = lazy(() => import("./pages/AdminPage"));

export const routes: RouteObject[] = [
  { index: true, element: <Navigate to="apply" replace /> },
  { path: "apply", element: <ApplyPage /> },
  { path: "mine", element: <MyLeavePage /> },
  { path: "balances", element: <BalancesPage /> },
  { path: "tasks", element: <TasksPage /> },
  { path: "admin", element: <AdminPage /> },
];

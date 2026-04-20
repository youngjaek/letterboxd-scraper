export type CohortSummary = {
  id: number;
  label: string;
  member_count: number;
  created_at: string;
  updated_at?: string | null;
  seed_user_id?: number | null;
  seed_username?: string | null;
  current_task_id?: string | null;
  current_task_stage?: string | null;
};

export type CohortMemberProfile = {
  username: string;
  avatar_url: string | null;
};

export type CohortDetail = CohortSummary & {
  members: CohortMemberProfile[];
  seed_username?: string | null;
};

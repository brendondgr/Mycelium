export type AuthUser = {
  id: number;
  username: string;
  email: string;
  is_staff: boolean;
  is_superuser: boolean;
};

export type AuthErrorBody = {
  non_field_errors?: string[];
  detail?: string;
};

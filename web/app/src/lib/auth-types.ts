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

export type AccountType = "personal" | "lab" | "department";

export type RegisterInput = {
  username: string;
  email: string;
  password: string;
  password_confirm: string;
  first_name?: string;
  last_name?: string;
  account_type: AccountType;
  org_name?: string;
  institution?: string;
};

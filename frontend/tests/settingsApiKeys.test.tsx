import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SettingsPanel } from "../src/components/Settings";

const setLlmModel = vi.fn();
const resetLlmModel = vi.fn();
const mutateAsync = vi.fn();

vi.mock("@/state/settingsHooks", () => ({
  useSettings: () => ({
    llmModel: "google/gemma-4-31b-it",
    setLlmModel,
    resetLlmModel,
  }),
}));

vi.mock("@/lib/queries", () => ({
  useLlmModels: () => ({
    data: { models: [] },
    isLoading: false,
    error: null,
  }),
  useLlmDefault: () => ({
    data: {
      llmAvailable: true,
      defaultModel: "google/gemma-4-31b-it",
      baseUrl: "https://openrouter.ai/api/v1",
    },
    isLoading: false,
  }),
  useUpdateApiKey: () => ({
    mutateAsync,
    isPending: false,
    error: null,
  }),
}));

describe("SettingsPanel API key section", () => {
  beforeEach(() => {
    mutateAsync.mockReset();
  });

  it("uses a masked input for API key values", () => {
    render(<SettingsPanel onClose={() => undefined} />);
    expect(screen.getByLabelText(/new api key value/i)).toHaveAttribute("type", "password");
  });

  it("shows confirmation modal and retries with confirmation", async () => {
    mutateAsync
      .mockResolvedValueOnce({
        updated: false,
        created: false,
        restartRequired: false,
        requiresConfirmation: true,
        confirmationType: "overwrite",
        message: "Confirm overwrite",
      })
      .mockResolvedValueOnce({
        updated: true,
        created: false,
        restartRequired: true,
        requiresConfirmation: false,
        confirmationType: null,
        message: "Updated",
      });

    render(<SettingsPanel onClose={() => undefined} />);
    const user = userEvent.setup();

    await user.selectOptions(
      screen.getByLabelText(/api key name/i),
      "OPENROUTER_API_KEY",
    );
    await user.type(screen.getByLabelText(/new api key value/i), "secret");
    await user.click(screen.getByRole("button", { name: /update key/i }));

    expect(await screen.findByText(/confirm overwrite of existing key/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /^confirm$/i }));

    await waitFor(() => {
      expect(mutateAsync).toHaveBeenCalledTimes(2);
    });
    expect(mutateAsync).toHaveBeenLastCalledWith(
      expect.objectContaining({ confirmOverwrite: true }),
    );
    expect(screen.getByText(/restart backend after successful save/i)).toBeInTheDocument();
  });
});


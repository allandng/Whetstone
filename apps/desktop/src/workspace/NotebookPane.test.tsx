import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NotebookPane, type NotebookCell } from "./NotebookPane";

function cell(overrides: Partial<NotebookCell> = {}): NotebookCell {
  return {
    id: "c1",
    language: "python",
    content: 'print("hi")',
    output: null,
    status: "",
    running: false,
    note: null,
    ...overrides,
  };
}

function renderPane(props: Partial<React.ComponentProps<typeof NotebookPane>> = {}) {
  const onAddCell = vi.fn();
  render(
    <NotebookPane
      cells={[cell()]}
      online
      adding={false}
      onChange={vi.fn()}
      onRun={vi.fn()}
      onCancel={vi.fn()}
      onClear={vi.fn()}
      onFocusCell={vi.fn()}
      onAddCell={onAddCell}
      {...props}
    />,
  );
  return { onAddCell };
}

describe("NotebookPane rendering", () => {
  it("renders one card per cell, in order, with its language and source", () => {
    renderPane({
      cells: [
        cell({ id: "a", language: "python", content: "print(1)" }),
        cell({ id: "b", language: "cpp", content: "int main(){}" }),
      ],
    });

    // Headers are labelled "Cell NN · <language>".
    expect(screen.getByText("Cell 01 · python")).toBeInTheDocument();
    expect(screen.getByText("Cell 02 · cpp")).toBeInTheDocument();

    // Each card's source textarea carries that cell's content.
    expect((screen.getByLabelText("Cell 01 source") as HTMLTextAreaElement).value).toBe(
      "print(1)",
    );
    expect((screen.getByLabelText("Cell 02 source") as HTMLTextAreaElement).value).toBe(
      "int main(){}",
    );

    // Footer count reflects the number of cells.
    expect(screen.getByText("2 cells · loopback mode")).toBeInTheDocument();
  });
});

describe("NotebookPane add-cell", () => {
  it("requests a Python cell when the Python button is clicked", async () => {
    const { onAddCell } = renderPane();
    await userEvent.click(screen.getByRole("button", { name: "Python" }));
    expect(onAddCell).toHaveBeenCalledTimes(1);
    expect(onAddCell).toHaveBeenCalledWith("python");
  });

  it("requests a C++ cell when the C++ button is clicked", async () => {
    const { onAddCell } = renderPane();
    await userEvent.click(screen.getByRole("button", { name: "C++" }));
    expect(onAddCell).toHaveBeenCalledWith("cpp");
  });

  it("disables the add controls while offline so cells can't be added", async () => {
    const { onAddCell } = renderPane({ online: false });
    const python = screen.getByRole("button", { name: "Python" });
    expect(python).toBeDisabled();
    await userEvent.click(python);
    expect(onAddCell).not.toHaveBeenCalled();
  });
});

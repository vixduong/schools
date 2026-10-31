# How should the five core screens look and behave?

Type: prototype
Status: resolved
Blocked by: 04, 07

## Question

Build a static clickable HTML prototype, Vietnamese UI copy, of: login by School (subdomain), teacher dashboard, gradebook (including the locked/approved states as ticket cards), student profile, parent view. Use the design system. React to it with the user to settle layout, navigation and state presentation. Output: `prototype/` linked from this ticket.

## Comments

- Prototype built (throwaway) on branch `prototype/core-screens`, folder `prototype/`; open `prototype/index.html` from a checkout of that branch (a worktree sits at `.claude/worktrees/prototype-core-screens/`). Five screens per the MVP: login by School, teacher home, gradebook with its workflow (Gửi duyệt moves it to Chờ duyệt and locks the cells), student profile (Ministry ID, masked national ID, Guardians, status history), Guardian view (phone first, a leave request becomes a waiting ticket). The teacher home has three structural variants via `?variant=`: A today's periods + things waiting, B a ticket board by state, C a class-first table. sloplint 0 FAIL. Waiting on the owner's pick and reactions.

## Answer

The owner chose **variant A with B's ticket board added** (built as variant D on branch `prototype/core-screens` to confirm it): today's periods + "Cần cô xử lý" tickets on top, a three-column state board (Đang nhập, Chờ người khác, Đã khoá) below. Gradebook, student profile, Guardian view and login were accepted as drawn. The decisions are folded into `DESIGN.md` § Screens; the prototype stays on its branch as the primary source and is not merged.

var dagcomponentfuncs = (window.dashAgGridComponentFunctions =
  window.dashAgGridComponentFunctions || {});

dagcomponentfuncs.WorkspaceRequestRole = function (props) {
  return React.createElement(
    "select",
    {
      className: "admin-row-select",
      "aria-label": "Grant Role for " + props.data.email,
      value: props.value || "viewer",
      onKeyDown: (event) => event.stopPropagation(),
      onChange: (event) =>
        props.node.setDataValue("grant_role", event.target.value),
    },
    props.roles.map((role) =>
      React.createElement(
        "option",
        { key: role.value, value: role.value },
        role.label,
      ),
    ),
  );
};

dagcomponentfuncs.WorkspaceRequestDecision = function (props) {
  return React.createElement(
    "select",
    {
      className: "admin-row-select",
      "aria-label": "Decision for " + props.data.email,
      value: "",
      onKeyDown: (event) => event.stopPropagation(),
      onChange: (event) => {
        if (!event.target.value) return;
        props.api.stopEditing();
        props.setData({
          request_id: props.data.id,
          role: props.node.data.grant_role || "viewer",
          decision: event.target.value,
          reason: props.node.data.decision_note || "",
        });
      },
    },
    [
      React.createElement(
        "option",
        { key: "", value: "", disabled: true },
        "Choose Decision",
      ),
      React.createElement(
        "option",
        { key: "approved", value: "approved" },
        "Approve",
      ),
      React.createElement(
        "option",
        { key: "rejected", value: "rejected" },
        "Reject",
      ),
    ],
  );
};

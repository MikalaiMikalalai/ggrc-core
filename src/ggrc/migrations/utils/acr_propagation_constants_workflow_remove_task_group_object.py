# Copyright (C) 2019 Google Inc.
# Licensed under http://www.apache.org/licenses/LICENSE-2.0 <see LICENSE file>

"""Module for keeping constants for ACR propagation rules

DO NOT MODIFY THESE VALUES.

These are just the common propagation dictionaries, that are used in different
migration files.

For migration consistency, do not update these values once they are merged.
If a modification is needed feel free to use these and modify them inside the
migration file, or add new common roles and propagation rules.
"""

CURRENT_PROPAGATION = {
    "Workflow": {
        "Admin": {
            "Relationship RUD": {
                "TaskGroup RUD": {
                    "Relationship RUD": {
                        "TaskGroupObject RUD": {
                        },
                        "TaskGroupTask RUD": {
                        },
                    },
                },
                "Cycle RUD": {
                    "Relationship RUD": {
                        "CycleTaskGroup RUD": {
                            "Relationship RUD": {
                                "CycleTaskGroupObjectTask RUD": {
                                    "Relationship RUD": {
                                        "Comment RUD": {
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
            },
        },
        "Workflow Member": {
            "Relationship R": {
                "Cycle R": {
                    "Relationship R": {
                        "CycleTaskGroup R": {
                            "Relationship R": {
                                "CycleTaskGroupObjectTask R": {
                                    "Relationship R": {
                                        "Comment R": {
                                        },
                                    },
                                },
                            },
                        },
                    },
                },
                "TaskGroup R": {
                    "Relationship R": {
                        "TaskGroupObject R": {
                        },
                        "TaskGroupTask R": {
                        },
                    },
                },
            },
        },
    },
}


WORKFLOW_PROPAGATION = {
    "Workflow": {
        "Admin": {
            "Relationship RUD": {
                "Cycle RUD": {
                    "Relationship RUD": {
                        "CycleTaskGroup RUD": {
                            "Relationship RUD": {
                                "CycleTaskGroupObjectTask RUD": {
                                    "Relationship RUD": {
                                        "Comment RUD": {}
                                    }
                                }
                            }
                        }
                    }
                },
                "TaskGroup RUD": {
                    "Relationship RUD": {
                        "TaskGroupTask RUD": {},
                    }
                }
            }
        },
        "Workflow Member": {
            "Relationship R": {
                "TaskGroup R": {
                    "Relationship R": {
                        "TaskGroupTask R": {},
                    }
                },
                "Cycle R": {
                    "Relationship R": {
                        "CycleTaskGroup R": {
                            "Relationship R": {
                                "CycleTaskGroupObjectTask R": {
                                    "Relationship R": {
                                        "Comment R": {}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

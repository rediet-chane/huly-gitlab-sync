from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class GitLabIssueEvent:
    """GitLab issue event data"""
    iid: int
    title: str
    description: str
    state: str
    author: str
    project: str
    url: Optional[str] = None
    
    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> 'GitLabIssueEvent':
        """Create from GitLab webhook payload"""
        issue_data = payload.get('object_attributes', {})
        project_data = payload.get('project', {})
        
        return cls(
            iid=issue_data.get('iid', 0),
            title=issue_data.get('title', ''),
            description=issue_data.get('description', ''),
            state=issue_data.get('state', 'opened'),
            author=issue_data.get('author', {}).get('username', 'unknown'),
            project=project_data.get('name', 'unknown'),
            url=issue_data.get('url')
        )
    
    def get_huly_status(self) -> str:
        """Map GitLab status to Huly status"""
        status_map = {
            "opened": "Todo",
            "closed": "Done",
            "reopened": "Todo"
        }
        return status_map.get(self.state, "Todo")
    
    def get_huly_description(self) -> str:
        """Format description for Huly"""
        return f"{self.description}\n\n---\n**Source**: GitLab\n**Issue**: #{self.iid}\n**URL**: {self.url}"
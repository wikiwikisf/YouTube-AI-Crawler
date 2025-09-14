import os
import json
import requests
from datetime import datetime, timedelta
import csv
from collections import defaultdict
import time
import schedule
from dataclasses import dataclass
from typing import List, Dict
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import sys
from pathlib import Path

@dataclass
class YouTubeVideo:
    video_id: str
    title: str
    channel_name: str
    channel_id: str
    published_at: str
    view_count: int
    like_count: int
    comment_count: int
    duration: str
    description: str
    url: str
    thumbnail_url: str
    relevance_score: float = 0.0

class YouTubeAICrawler:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://www.googleapis.com/youtube/v3"
        self.ai_keywords = [
            "artificial intelligence", "AI news", "machine learning", "deep learning",
            "neural networks", "OpenAI", "ChatGPT", "GPT", "LLM", "large language model",
            "AI breakthrough", "AI development", "AI research", "generative AI",
            "computer vision", "natural language processing", "NLP", "AI ethics",
            "AI regulation", "AI startup", "AI company", "AI technology"
        ]
        
        # Popular AI channels to prioritize
        self.ai_channels = [
            "Two Minute Papers",
            "Yannic Kilcher",
            "AI Explained",
            "Machine Learning Street Talk",
            "Lex Fridman",
            "The AI Advantage",
            "AI Coffee Break",
            "DeepMind",
            "OpenAI",
            "Artificial Intelligence News"
        ]
    
    def search_videos(self, query: str, days_back: int = 7, max_results: int = 50) -> List[YouTubeVideo]:
        """Search for videos related to AI in the past week"""
        
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)
        
        url = f"{self.base_url}/search"
        params = {
            'part': 'snippet',
            'q': query,
            'type': 'video',
            'order': 'relevance',
            'publishedAfter': start_date.isoformat() + 'Z',
            'publishedBefore': end_date.isoformat() + 'Z',
            'maxResults': max_results,
            'key': self.api_key
        }
        
        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
            
            videos = []
            for item in data.get('items', []):
                video = self._parse_video_item(item)
                if video:
                    videos.append(video)
            
            return videos
            
        except requests.exceptions.RequestException as e:
            print(f"Error searching videos: {e}")
            return []
    
    def get_video_statistics(self, video_ids: List[str]) -> Dict[str, dict]:
        """Get detailed statistics for videos"""
        if not video_ids:
            return {}
        
        # YouTube API allows up to 50 video IDs per request
        video_stats = {}
        
        for i in range(0, len(video_ids), 50):
            batch_ids = video_ids[i:i+50]
            
            url = f"{self.base_url}/videos"
            params = {
                'part': 'statistics,contentDetails',
                'id': ','.join(batch_ids),
                'key': self.api_key
            }
            
            try:
                response = requests.get(url, params=params)
                response.raise_for_status()
                data = response.json()
                
                for item in data.get('items', []):
                    video_id = item['id']
                    stats = item.get('statistics', {})
                    content_details = item.get('contentDetails', {})
                    
                    video_stats[video_id] = {
                        'view_count': int(stats.get('viewCount', 0)),
                        'like_count': int(stats.get('likeCount', 0)),
                        'comment_count': int(stats.get('commentCount', 0)),
                        'duration': content_details.get('duration', 'PT0S')
                    }
                
                # Rate limiting
                time.sleep(0.1)
                
            except requests.exceptions.RequestException as e:
                print(f"Error getting video statistics: {e}")
        
        return video_stats
    
    def _parse_video_item(self, item: dict) -> YouTubeVideo:
        """Parse video item from YouTube API response"""
        try:
            snippet = item['snippet']
            video_id = item['id']['videoId']
            
            return YouTubeVideo(
                video_id=video_id,
                title=snippet['title'],
                channel_name=snippet['channelTitle'],
                channel_id=snippet['channelId'],
                published_at=snippet['publishedAt'],
                view_count=0,  # Will be updated later
                like_count=0,
                comment_count=0,
                duration='',
                description=snippet.get('description', ''),
                url=f"https://www.youtube.com/watch?v={video_id}",
                thumbnail_url=snippet['thumbnails']['high']['url']
            )
        except KeyError as e:
            print(f"Error parsing video item: {e}")
            return None
    
    def crawl_ai_news(self, days_back: int = 7) -> List[YouTubeVideo]:
        """Crawl YouTube for AI news videos"""
        all_videos = []
        
        print(f"Searching for AI videos from the past {days_back} days...")
        
        # Search with different AI-related queries
        search_queries = [
            "AI news this week",
            "artificial intelligence latest",
            "machine learning news",
            "AI breakthrough 2024",
            "ChatGPT GPT news",
            "AI development update"
        ]
        
        for query in search_queries:
            print(f"Searching for: {query}")
            videos = self.search_videos(query, days_back, max_results=30)
            all_videos.extend(videos)
            time.sleep(1)  # Rate limiting
        
        # Remove duplicates
        unique_videos = {}
        for video in all_videos:
            if video.video_id not in unique_videos:
                unique_videos[video.video_id] = video
        
        video_list = list(unique_videos.values())
        
        # Get detailed statistics
        video_ids = [v.video_id for v in video_list]
        stats = self.get_video_statistics(video_ids)
        
        # Update videos with statistics and calculate relevance scores
        for video in video_list:
            if video.video_id in stats:
                stat_data = stats[video.video_id]
                video.view_count = stat_data['view_count']
                video.like_count = stat_data['like_count']
                video.comment_count = stat_data['comment_count']
                video.duration = stat_data['duration']
            
            video.relevance_score = self._calculate_relevance_score(video)
        
        return video_list
    
    def _calculate_relevance_score(self, video: YouTubeVideo) -> float:
        """Calculate relevance score based on various factors"""
        score = 0.0
        
        # View count factor (normalized)
        if video.view_count > 0:
            score += min(video.view_count / 10000, 10)  # Cap at 10 points
        
        # Like ratio factor
        if video.view_count > 0 and video.like_count > 0:
            like_ratio = video.like_count / video.view_count
            score += like_ratio * 100  # Scale up
        
        # Channel reputation factor
        if video.channel_name in self.ai_channels:
            score += 5
        
        # Title keyword relevance
        title_lower = video.title.lower()
        keyword_matches = sum(1 for keyword in self.ai_keywords 
                            if keyword.lower() in title_lower)
        score += keyword_matches * 2
        
        # Recency factor (newer videos get slight boost)
        try:
            pub_date = datetime.fromisoformat(video.published_at.replace('Z', '+00:00'))
            days_old = (datetime.now(pub_date.tzinfo) - pub_date).days
            if days_old <= 2:
                score += 3
            elif days_old <= 7:
                score += 1
        except:
            pass
        
        return score
    
    def filter_top_videos(self, videos: List[YouTubeVideo], count: int = 10) -> List[YouTubeVideo]:
        """Filter and return top videos by relevance score"""
        # Sort by relevance score (descending)
        sorted_videos = sorted(videos, key=lambda x: x.relevance_score, reverse=True)
        return sorted_videos[:count]

class WeeklyPublisher:
    def __init__(self, smtp_server: str = None, smtp_port: int = 587, 
                 email_user: str = None, email_password: str = None):
        self.smtp_server = smtp_server
        self.smtp_port = smtp_port
        self.email_user = email_user
        self.email_password = email_password
    
    def generate_html_report(self, videos: List[YouTubeVideo]) -> str:
        """Generate HTML report of top AI videos"""
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Weekly AI News - YouTube Roundup</title>
            <style>
                body {{ font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }}
                .header {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; }}
                .video-item {{ border: 1px solid #ddd; margin: 20px 0; padding: 15px; border-radius: 8px; }}
                .video-title {{ font-size: 18px; font-weight: bold; margin-bottom: 10px; }}
                .video-meta {{ color: #666; font-size: 14px; margin-bottom: 10px; }}
                .video-stats {{ background: #f5f5f5; padding: 10px; border-radius: 5px; }}
                .thumbnail {{ float: left; margin-right: 15px; border-radius: 5px; }}
                .clear {{ clear: both; }}
                a {{ color: #1976d2; text-decoration: none; }}
                a:hover {{ text-decoration: underline; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>🤖 Weekly AI News Roundup</h1>
                <p>Top {len(videos)} AI videos from YouTube this week</p>
                <p>Generated on {datetime.now().strftime('%B %d, %Y')}</p>
            </div>
        """
        
        for i, video in enumerate(videos, 1):
            # Parse duration
            duration = self._parse_duration(video.duration)
            
            html += f"""
            <div class="video-item">
                <img src="{video.thumbnail_url}" alt="Thumbnail" class="thumbnail" width="120" height="90">
                <div class="video-title">
                    {i}. <a href="{video.url}" target="_blank">{video.title}</a>
                </div>
                <div class="video-meta">
                    📺 {video.channel_name} | 📅 {self._format_date(video.published_at)} | ⏱️ {duration}
                </div>
                <div class="video-stats">
                    👀 {video.view_count:,} views | 
                    👍 {video.like_count:,} likes | 
                    💬 {video.comment_count:,} comments |
                    📊 Score: {video.relevance_score:.1f}
                </div>
                <div class="clear"></div>
            </div>
            """
        
        html += """
            <div style="margin-top: 30px; text-align: center; color: #666;">
                <p>This report was automatically generated by YouTube AI News Crawler</p>
            </div>
        </body>
        </html>
        """
        
        return html
    
    def _parse_duration(self, duration: str) -> str:
        """Parse YouTube duration format (PT4M13S) to readable format"""
        if not duration or duration == 'PT0S':
            return "Unknown"
        
        import re
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        if not match:
            return duration
        
        hours, minutes, seconds = match.groups()
        
        parts = []
        if hours:
            parts.append(f"{hours}h")
        if minutes:
            parts.append(f"{minutes}m")
        if seconds:
            parts.append(f"{seconds}s")
        
        return " ".join(parts) if parts else "0s"
    
    def _format_date(self, date_str: str) -> str:
        """Format date string to readable format"""
        try:
            date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return date.strftime('%b %d, %Y')
        except:
            return date_str
    
    def save_report(self, videos: List[YouTubeVideo], filename: str = None):
        """Save report to HTML file"""
        if not filename:
            date_str = datetime.now().strftime('%Y%m%d')
            filename = f"ai_news_weekly_{date_str}.html"
        
        html_content = self.generate_html_report(videos)
        
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html_content)
        
        print(f"Report saved to {filename}")
        return filename
    
    def send_email_report(self, videos: List[YouTubeVideo], recipients: List[str], 
                         subject: str = None):
        """Send email report"""
        if not all([self.smtp_server, self.email_user, self.email_password]):
            print("Email configuration not set up")
            return False
        
        if not subject:
            subject = f"Weekly AI News Roundup - {datetime.now().strftime('%B %d, %Y')}"
        
        html_content = self.generate_html_report(videos)
        
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.email_user
            msg['To'] = ', '.join(recipients)
            
            html_part = MIMEText(html_content, 'html')
            msg.attach(html_part)
            
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.email_user, self.email_password)
                server.send_message(msg)
            
            print(f"Email sent to {len(recipients)} recipients")
            return True
            
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

def main():
    """Main function to run the crawler and publisher"""
    
    # Configuration - set these as environment variables or config file
    YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY', 'your_youtube_api_key_here')
    
    # Email configuration (optional)
    EMAIL_CONFIG = {
        'smtp_server': os.getenv('SMTP_SERVER', 'smtp.gmail.com'),
        'smtp_port': int(os.getenv('SMTP_PORT', 587)),
        'email_user': os.getenv('EMAIL_USER'),
        'email_password': os.getenv('EMAIL_PASSWORD')
    }
    
    # Recipients for email reports
    EMAIL_RECIPIENTS = os.getenv('EMAIL_RECIPIENTS', '').split(',')
    EMAIL_RECIPIENTS = [email.strip() for email in EMAIL_RECIPIENTS if email.strip()]
    
    if YOUTUBE_API_KEY == 'your_youtube_api_key_here':
        print("Please set your YouTube API key in the YOUTUBE_API_KEY environment variable")
        return
    
    # Initialize crawler and publisher
    crawler = YouTubeAICrawler(YOUTUBE_API_KEY)
    publisher = WeeklyPublisher(**EMAIL_CONFIG)
    
    print("Starting weekly AI news crawl...")
    
    # Crawl for videos from the past 7 days
    all_videos = crawler.crawl_ai_news(days_back=7)
    
    if not all_videos:
        print("No videos found")
        return
    
    # Get top 15 videos
    top_videos = crawler.filter_top_videos(all_videos, count=15)
    
    print(f"\nFound {len(all_videos)} videos, selected top {len(top_videos)}")
    
    # Generate and save report
    report_file = publisher.save_report(top_videos)
    
    # Send email if configured
    if EMAIL_RECIPIENTS and all(EMAIL_CONFIG.values()):
        publisher.send_email_report(top_videos, EMAIL_RECIPIENTS)
    
    # Print summary
    print(f"\nTop {len(top_videos)} AI videos this week:")
    for i, video in enumerate(top_videos[:5], 1):  # Show top 5 in console
        print(f"{i}. {video.title}")
        print(f"   Channel: {video.channel_name}")
        print(f"   Views: {video.view_count:,} | Score: {video.relevance_score:.1f}")
        
        # Show most replayed section if available
        #if video.most_replayed_segment:
        #    segment = video.most_replayed_segment
        #    print(f"   🔥 Most Replayed: {segment['peak_time_formatted']} (Engagement: {segment['intensity']*100:.0f}%)")
        #    print(f"   🎯 Jump to peak: {video.timestamped_url}")
        
        print(f"   🔗 URL: {video.url}")
        print()

def run_weekly_scheduler():
    """Set up weekly scheduler"""
    schedule.every().monday.at("09:00").do(main)
    
    print("Scheduler started - will run every Monday at 9:00 AM")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(3600)  # Check every hour
    except KeyboardInterrupt:
        print("Scheduler stopped")

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == 'schedule':
        run_weekly_scheduler()
    else:
        main()

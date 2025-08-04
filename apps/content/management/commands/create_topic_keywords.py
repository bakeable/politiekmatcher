import math
import re
import string
from collections import Counter
from collections import defaultdict

import spacy
from django.core.management.base import BaseCommand
from apps.content.models import Topic
from apps.content.models import TopicKeyword

nlp = spacy.load("nl_core_news_sm")

# domain-specific words to manually exclude
CUSTOM_STOPWORDS = {
    "verkiezingsprogramma",
    "nederland",
    "partij",
    "gaan",
    "komen",
    "maken",
    "mens",
    "willen",
    "moeten",
    "zullen",
    "kunnen",
    "groot",
    "hoog",
    "nodig",
    "goed",
    "overheid",
    "politiek",
    "regering",
    "land",
    "nieuw",
    "jaar",
    "tijd",
    "veel",
    "breed",
    "probleem",
    "oplossing",
    "belangrijk",
    "vraag",
    "antwoord",
    "standpunt",
    "standpunten",
    "thema",
}

ACCEPTED_POS = {
    "NOUN",
    "PROPN",
    "ADJ",
}  # only nouns, proper nouns, adjectives


class Command(BaseCommand):
    help = "Generate the 10 most common meaningful words per Topic"

    def handle(self, *args, **kwargs):
        all_keywords = defaultdict(
            lambda: defaultdict(int)
        )  # {keyword: {topic_id: count}}

        for topic in Topic.objects.prefetch_related(
            "themes__statements__positions"
        ).all():
            self.stdout.write(f"\n🔍 Analyzing topic: {topic.name}")
            texts = []

            for theme in topic.themes.all():
                if theme.name:
                    texts.append(theme.name)
                if theme.description:
                    texts.append(theme.description)
                if theme.context:
                    texts.append(theme.context)

                for statement in theme.statements.all():
                    if statement.text:
                        texts.append(statement.text)
                    if statement.explanation:
                        texts.append(statement.explanation)

                    for pos in statement.positions.all():
                        if pos.explanation:
                            texts.append(pos.explanation)

            full_text = " ".join(texts)
            doc = nlp(full_text)

            for token in doc:
                if (
                    token.is_alpha
                    and not token.is_stop
                    and token.lemma_.lower() not in CUSTOM_STOPWORDS
                    and token.pos_ in ACCEPTED_POS
                    and len(token) > 2
                ):
                    keyword = token.lemma_.lower()
                    all_keywords[keyword][topic.id] += 1

        # Filter keywords that clearly have 1 dominant topic
        topic_map = defaultdict(list)  # topic_id: [(keyword, count)]

        for keyword, topic_counts in all_keywords.items():
            if len(topic_counts) == 1:
                topic_id = list(topic_counts.keys())[0]
                topic_map[topic_id].append((keyword, topic_counts[topic_id]))
            else:
                sorted_topics = sorted(topic_counts.items(), key=lambda x: -x[1])
                if sorted_topics[0][1] >= sorted_topics[1][1] * 2:
                    topic_map[sorted_topics[0][0]].append(
                        (keyword, sorted_topics[0][1])
                    )
                # otherwise ignore (distributed)

        # Create TopicKeyword entries per topic with relevance_score
        for topic in Topic.objects.all():
            keywords = topic_map.get(topic.id, [])
            keywords.sort(key=lambda x: -x[1])

            if not keywords:
                continue

            # Normalize based on highest score
            max_count = keywords[0][1]
            topic_keywords = []

            size = len(keywords)
            if size < 10:
                top_n = size
            elif size < 20:
                top_n = 10
            elif size < 40:
                top_n = 20
            else:
                top_n = 30

            self.stdout.write(
                f"\n📊 Topic '{topic.name}' - top {top_n} of {size} unique keywords:"
            )

            for word, count in keywords[:top_n]:
                score = round(math.log(count) / math.log(max_count), 4)
                self.stdout.write(f"   {word}: {count} (score: {score})")
                topic_keywords.append(
                    TopicKeyword(
                        topic=topic,
                        keyword=word,
                        relevance_score=score,
                    )
                )

            #
            TopicKeyword.objects.filter(topic=topic).delete()
            TopicKeyword.objects.bulk_create(topic_keywords)

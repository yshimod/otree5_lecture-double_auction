from otree.api import *
import time
import random

from sqlalchemy import true


doc = "Double auction market"


class C(BaseConstants):
    NAME_IN_URL = 'double_auction_with_comment'
    PLAYERS_PER_GROUP = None
    NUM_ROUNDS = 1 
    ITEMS_PER_SELLER = 3  # 財の数
    VALUATION_MIN = cu(50) # 支払意思額の下限パラメータ
    VALUATION_MAX = cu(110) # 支払意思額の上限パラメータ
    PRODUCTION_COSTS_MIN = cu(10) # 機械費用の下限パラメータ
    PRODUCTION_COSTS_MAX = cu(80) # 機械費用の下限パラメータ


class Subsession(BaseSubsession):
    pass


def creating_session(subsession: Subsession):
    players = subsession.get_players() # 全プレーヤー
    for p in players:
        # this means if the player's ID is not a multiple of 2, they are a buyer.
        # for more buyers, change the 2 to 3
        p.is_buyer = p.id_in_group % 2 > 0 # プレーヤーidのmodが0(1:偶数)でない場合は Ture
        if p.is_buyer: # 買手
            p.num_items = 0 # 買手の初期所有は0
            p.break_even_point = random.randint(C.VALUATION_MIN, C.VALUATION_MAX) # 支払意志額を決定
            p.current_offer = 0 # 初期オファーを0とする。
        else: # 売手
            p.num_items = C.ITEMS_PER_SELLER # 売手の初期所有は3
            p.break_even_point = random.randint(
                C.PRODUCTION_COSTS_MIN, C.PRODUCTION_COSTS_MAX
            ) #　機械費用を決定
            p.current_offer = C.VALUATION_MAX + 1 #　初期オファーは支払意志額の上限+1


class Group(BaseGroup):
    start_timestamp = models.IntegerField()


class Player(BasePlayer):
    is_buyer = models.BooleanField()
    current_offer = models.CurrencyField()
    break_even_point = models.CurrencyField()
    num_items = models.IntegerField()


class Transaction(ExtraModel):
    group = models.Link(Group)
    buyer = models.Link(Player)
    seller = models.Link(Player)
    price = models.CurrencyField()
    seconds = models.IntegerField(doc="Timestamp (seconds since beginning of trading)")


def find_match(buyers, sellers):
    for buyer in buyers:
        for seller in sellers:
            if seller.num_items > 0 and seller.current_offer <= buyer.current_offer: 
                # return as soon as we find a match (the rest of the loop will be skipped)
                return [buyer, seller]


def live_method(player: Player, data):         
    group = player.group # ①
    players = group.get_players()
    buyers = [p for p in players if p.is_buyer] # 買手リスト一覧
    sellers = [p for p in players if not p.is_buyer] # 売手リスト一覧
    news = None    
    if data: # オファー情報がある場合の処理
        print("dataきた",data)
        offer = int(data['offer']) # オファー情報を受け取り
        player.current_offer = offer # オファー情報をDBに保存
        if player.is_buyer: # 買手の場合の処理
            match = find_match(buyers=[player], sellers=sellers)
        else: # 売手の場合の処理
            match = find_match(buyers=buyers, sellers=[player])
        if match: 
            print("mathきた",match)
            [buyer, seller] = match #  ②buyer = buyer, ③seller = seller として保存
            price = buyer.current_offer # ④買手の提示価格
            Transaction.create( # グループ全体の取引履歴を作成
                group=group, # ①
                buyer=buyer, # ②
                seller=seller, # ③
                price=price, # ④
                seconds=int(time.time() - group.start_timestamp),
            ) 
            buyer.num_items += 1 # 買手の保有量に+1
            seller.num_items -= 1 # 売手の保有量を-1
            buyer.payoff += buyer.break_even_point - price  # 買手の利益
            seller.payoff += price - seller.break_even_point # 売手の利益
            buyer.current_offer = 0 # 買手のオファーを初期化
            seller.current_offer = C.VALUATION_MAX + 1 # 売手のオファーを初期化
            news = dict(buyer=buyer.id_in_group, seller=seller.id_in_group, price=price)

    bids = sorted([p.current_offer for p in buyers if p.current_offer > 0], reverse=True) # 買手の入札列
    asks = sorted([p.current_offer for p in sellers if p.current_offer <= C.VALUATION_MAX]) # 売手の入札列
    highcharts_series = [[tx.seconds, tx.price] for tx in Transaction.filter(group=group)] # グループの取引履歴を呼び出し。

    return {
        p.id_in_group: dict(
            num_items=p.num_items,
            current_offer=p.current_offer,
            payoff=p.payoff,
            bids=bids,
            asks=asks,
            highcharts_series=highcharts_series,
            news=news,
        )
        for p in players
    }


# PAGES
class WaitToStart(WaitPage):
    @staticmethod
    def after_all_players_arrive(group: Group):
        group.start_timestamp = int(time.time())


class Trading(Page):
    live_method = live_method

    @staticmethod
    def js_vars(player: Player):
        return dict(id_in_group=player.id_in_group, is_buyer=player.is_buyer)

    @staticmethod
    def get_timeout_seconds(player: Player):
        import time

        group = player.group
        return (group.start_timestamp + 2 * 60) - time.time()


class ResultsWaitPage(WaitPage):
    pass


class Results(Page):
    pass


page_sequence = [WaitToStart, Trading, ResultsWaitPage, Results]

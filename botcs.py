import discord
from discord.ext import commands
from discord.ui import View, Button, Select, Modal, TextInput
import datetime
import asyncio
import os

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)

# ID из вашего сервера
TICKET_PANEL_CHANNEL_ID = 1477835412012793856  # Канал для панели
TICKET_CATEGORY_ID = 1477835280315842792      # Категория для тикетов
GUILD_ID = 1477729837597720604  # ID вашего сервера (нужно заменить на реальный)

# Роли персонала
STAFF_ROLES = [
    1477825566408310974,  # Модератор
    1477828939551473786,  # Администратор
    1477827609927745677, 
    1477827889557672106,  
    1477729837597720607,  # Роль для приема заявок
    1477828744390512711,  # Роль для приема заявок
]

# Роль при принятии заявки
APPLICANT_ROLE_ID = 1477845619874856991

# Роли для приема заявок (только эти могут принимать/отклонять)
APPLICATION_MANAGER_ROLES = [
    1477729837597720607,  # Роль для приема заявок
    1477828744390512711,  # Роль для приема заявок
]

# Хранилище активных тикетов
active_tickets = {}

# ========== КЛАССЫ ДЛЯ ЗАЯВЛЕНИЙ ==========
class ApplicationModal(Modal):
    """Модальное окно для заполнения заявления"""
    def __init__(self, position: str):
        super().__init__(title=f"Заявление на должность: {position}")
        self.position = position
        
        self.add_item(TextInput(label="Ваше имя", placeholder="Введите ваше имя...", required=True))
        self.add_item(TextInput(label="Ваш возраст", placeholder="Сколько вам лет?", required=True))
        self.add_item(TextInput(label="Как давно играете на сервере", placeholder="Например: 3 месяца", required=True))
        self.add_item(TextInput(label="Причина подачи заявления", placeholder="Почему хотите стать частью команды?", style=discord.TextStyle.paragraph, required=True))
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        
        # Собираем данные
        name = self.children[0].value
        age = self.children[1].value
        playtime = self.children[2].value
        reason = self.children[3].value
        
        # Отправляем заявку админам с ролями 1477729837597720607 и 1477828744390512711
        await send_application_to_admins(interaction, self.position, name, age, playtime, reason)
        
        await interaction.followup.send("✅ Ваше заявление отправлено на рассмотрение!", ephemeral=True)

class ApplicationSelect(Select):
    """Выбор должности для заявления"""
    def __init__(self):
        options = [
            discord.SelectOption(label="📹 Медиа-команда", value="media", description="Создание контента, видео, оформление"),
            discord.SelectOption(label="🛡️ Младший модератор", value="junior_moder", description="Помощь в модерировании чата")
        ]
        super().__init__(placeholder="Выберите должность...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        # Открываем модальное окно
        await interaction.response.send_modal(ApplicationModal(self.values[0]))

class ApplicationView(View):
    """Панель подачи заявлений"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ApplicationSelect())

async def send_application_to_admins(interaction: discord.Interaction, position: str, name: str, age: str, playtime: str, reason: str):
    """Отправка заявки админам в ЛС"""
    guild = interaction.guild
    
    # Словарь для названий должностей
    position_names = {
        "media": "📹 Медиа-команда",
        "junior_moder": "🛡️ Младший модератор"
    }
    
    # Создаем Embed с заявкой
    embed = discord.Embed(
        title="📨 Новая заявка в команду",
        color=discord.Color.purple(),
        timestamp=datetime.datetime.now()
    )
    embed.add_field(name="👤 Отправитель", value=f"{interaction.user.name} ({interaction.user.id})", inline=False)
    embed.add_field(name="📋 Должность", value=position_names.get(position, position), inline=False)
    embed.add_field(name="📝 Имя", value=name, inline=True)
    embed.add_field(name="🎂 Возраст", value=age, inline=True)
    embed.add_field(name="⏰ На сервере", value=playtime, inline=True)
    embed.add_field(name="💭 Причина", value=reason, inline=False)
    embed.add_field(name="🆔 Сервер", value=guild.name, inline=False)
    embed.set_footer(text="Нажмите кнопки ниже для принятия/отказа")
    
    # Создаем кнопки для админов с информацией о сервере
    view = ApplicationResponseView(
        applicant_id=interaction.user.id,
        guild_id=guild.id,
        position=position,
        name=name,
        age=age,
        playtime=playtime,
        reason=reason
    )
    
    # Отправляем всем админам с нужными ролями
    sent_count = 0
    
    for role_id in APPLICATION_MANAGER_ROLES:
        role = guild.get_role(role_id)
        if role:
            for member in role.members:
                try:
                    await member.send(embed=embed, view=view)
                    sent_count += 1
                except Exception as e:
                    print(f"Не удалось отправить {member.name}: {e}")
    
    print(f"✅ Заявка отправлена {sent_count} админам")

class ApplicationResponseView(View):
    """Кнопки для ответа на заявку"""
    def __init__(self, applicant_id: int, guild_id: int, position: str, name: str, age: str, playtime: str, reason: str):
        super().__init__(timeout=None)
        self.applicant_id = applicant_id
        self.guild_id = guild_id
        self.position = position
        self.name = name
        self.age = age
        self.playtime = playtime
        self.reason = reason
    
    async def has_permission(self, user: discord.User) -> bool:
        """Проверка прав через сервер"""
        # Получаем сервер
        guild = bot.get_guild(self.guild_id)
        if not guild:
            return False
        
        # Получаем участника сервера
        member = guild.get_member(user.id)
        if not member:
            return False
        
        # Проверяем наличие нужных ролей
        for role_id in APPLICATION_MANAGER_ROLES:
            if member.get_role(role_id):
                return True
        
        # Проверка на администратора (на всякий случай)
        return member.guild_permissions.administrator
    
    @discord.ui.button(label="✅ Принять", style=discord.ButtonStyle.success, custom_id="accept_app")
    async def accept_application(self, interaction: discord.Interaction, button: Button):
        # Проверяем права через сервер
        if not await self.has_permission(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав для принятия заявок! Нужна специальная роль на сервере.", ephemeral=True)
            return
        
        # Получаем сервер
        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("❌ Сервер не найден!", ephemeral=True)
            return
        
        # Ищем пользователя на сервере
        member = guild.get_member(self.applicant_id)
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден на сервере!", ephemeral=True)
            return
        
        # Выдаем роль
        role = guild.get_role(APPLICANT_ROLE_ID)
        if role:
            await member.add_roles(role)
            
            # Уведомляем пользователя
            try:
                await member.send(f"✅ Поздравляем! Ваша заявка на должность **{self.position}** принята! Вам выдана роль.")
            except:
                pass
            
            # Отвечаем админу
            await interaction.response.send_message(f"✅ Заявка принята! Пользователю выдана роль.", ephemeral=True)
            
            # Отключаем кнопки
            for item in self.children:
                item.disabled = True
            await interaction.message.edit(view=self)
        else:
            await interaction.response.send_message("❌ Роль для выдачи не найдена!", ephemeral=True)
    
    @discord.ui.button(label="❌ Отказать", style=discord.ButtonStyle.danger, custom_id="reject_app")
    async def reject_application(self, interaction: discord.Interaction, button: Button):
        # Проверяем права через сервер
        if not await self.has_permission(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав для отказа в заявках! Нужна специальная роль на сервере.", ephemeral=True)
            return
        
        # Получаем сервер
        guild = bot.get_guild(self.guild_id)
        if not guild:
            await interaction.response.send_message("❌ Сервер не найден!", ephemeral=True)
            return
        
        # Уведомляем пользователя
        try:
            member = await bot.fetch_user(self.applicant_id)
            await member.send(f"❌ К сожалению, ваша заявка на должность **{self.position}** отклонена.")
        except:
            pass
        
        await interaction.response.send_message("❌ Заявка отклонена", ephemeral=True)
        
        # Отключаем кнопки
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(view=self)

# ========== КЛАССЫ ДЛЯ ТИКЕТОВ ==========
class TicketSelect(Select):
    """Выпадающее меню для выбора типа тикета"""
    def __init__(self):
        options = [
            discord.SelectOption(label="👤 Жалоба на игроков", value="player", description="Пожаловаться на другого игрока"),
            discord.SelectOption(label="🛡️ Жалоба на модерацию", value="moder", description="Пожаловаться на действия модератора"),
            discord.SelectOption(label="🔧 Технические неполадки", value="tech", description="Проблемы с ботами, баги"),
            discord.SelectOption(label="❓ Другой вопрос", value="other", description="Все остальные вопросы")
        ]
        super().__init__(placeholder="📋 Выберите категорию обращения...", min_values=1, max_values=1, options=options)
    
    async def callback(self, interaction: discord.Interaction):
        await create_ticket(interaction, self.values[0])

class TicketPanelView(View):
    """Панель создания тикетов"""
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(TicketSelect())

class TicketControlView(View):
    """Панель управления тикетом"""
    def __init__(self, ticket_owner_id: int):
        super().__init__(timeout=None)
        self.ticket_owner_id = ticket_owner_id
        self.is_accepted = False
        self.accepted_by = None
    
    def is_staff(self, user: discord.Member) -> bool:
        for role_id in STAFF_ROLES:
            if user.get_role(role_id):
                return True
        return False
    
    def can_close(self, user: discord.Member) -> bool:
        return (user.id == self.ticket_owner_id or self.is_staff(user) or user == bot.user)
    
    @discord.ui.button(label="✅ Принять тикет", style=discord.ButtonStyle.success, custom_id="accept_ticket")
    async def accept_ticket(self, interaction: discord.Interaction, button: Button):
        if not self.is_staff(interaction.user):
            await interaction.response.send_message("❌ Только персонал может принимать тикеты!", ephemeral=True)
            return
        
        if self.is_accepted:
            await interaction.response.send_message(f"❌ Тикет уже принят {self.accepted_by.mention}", ephemeral=True)
            return
        
        self.is_accepted = True
        self.accepted_by = interaction.user
        button.disabled = True
        await interaction.message.edit(view=self)
        
        embed = discord.Embed(
            title="✅ Тикет принят в обработку",
            description=f"Администратор {interaction.user.mention} принял тикет в обработку",
            color=discord.Color.green(),
            timestamp=datetime.datetime.now()
        )
        await interaction.channel.send(embed=embed)
        await interaction.response.send_message("✅ Вы приняли тикет в обработку", ephemeral=True)
    
    @discord.ui.button(label="🔒 Закрыть тикет", style=discord.ButtonStyle.danger, custom_id="close_ticket")
    async def close_ticket(self, interaction: discord.Interaction, button: Button):
        if not self.can_close(interaction.user):
            await interaction.response.send_message("❌ У вас нет прав для закрытия тикета!", ephemeral=True)
            return
        
        await interaction.response.send_message("🔒 Тикет будет закрыт через 5 секунд...")
        await asyncio.sleep(5)
        await interaction.channel.delete()

async def create_ticket(interaction: discord.Interaction, ticket_type: str):
    """Создание нового тикета"""
    try:
        guild = interaction.guild
        user = interaction.user
        category = guild.get_channel(TICKET_CATEGORY_ID)
        
        if not category:
            await interaction.response.send_message("❌ Категория для тикетов не найдена!", ephemeral=True)
            return
        
        for channel in category.channels:
            if channel.name.endswith(f"-{user.name.lower()}") and isinstance(channel, discord.TextChannel):
                await interaction.response.send_message(f"❌ У вас уже есть тикет: {channel.mention}", ephemeral=True)
                return
        
        type_names = {"player": "жалоба-игрок", "moder": "жалоба-модер", "tech": "технический", "other": "вопрос"}
        channel_name = f"{type_names.get(ticket_type, 'тикет')}-{user.name.lower()}"
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        staff_mentions = []
        for role_id in STAFF_ROLES:
            role = guild.get_role(role_id)
            if role:
                overwrites[role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
                staff_mentions.append(role.mention)
        
        channel = await guild.create_text_channel(
            name=channel_name,
            category=category,
            overwrites=overwrites,
            topic=f"Тикет от {user.name} | Тип: {ticket_type}"
        )
        
        active_tickets[channel.id] = {"user_id": user.id, "type": ticket_type}
        control_view = TicketControlView(user.id)
        
        type_desc = {
            "player": "👤 Жалоба на игроков",
            "moder": "🛡️ Жалоба на модерацию",
            "tech": "🔧 Технические неполадки",
            "other": "❓ Другой вопрос"
        }
        
        embed = discord.Embed(
            title="🎫 Новый тикет создан",
            description=f"**Здравствуйте, {user.mention}!**\n\n"
                       f"**Категория:** {type_desc.get(ticket_type, 'Неизвестно')}\n\n"
                       f"Опишите вашу проблему подробно. Наши сотрудники скоро ответят вам.\n\n"
                       f"**Доступные действия:**\n"
                       f"• **✅ Принять тикет** - только для персонала\n"
                       f"• **🔒 Закрыть тикет** - для создателя и персонала",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.now()
        )
        embed.set_footer(text="Спасибо за обращение!")
        
        await channel.send(
            content=f"{user.mention} {' '.join(staff_mentions)}",
            embed=embed,
            view=control_view
        )
        
        await interaction.response.send_message(f"✅ Тикет создан: {channel.mention}", ephemeral=True)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Ошибка: {str(e)}", ephemeral=True)

# ========== КОМАНДЫ ==========
@bot.command()
@commands.has_permissions(administrator=True)
async def setup(ctx):
    """Создание панели тикетов"""
    embed = discord.Embed(
        title="🎫 Система поддержки",
        description="Добро пожаловать в систему тикетов!\n\n"
                   "**Выберите категорию обращения:**\n"
                   "👤 **Жалоба на игроков** - нарушение правил игроками\n"
                   "🛡️ **Жалоба на модерацию** - действия модераторов\n"
                   "🔧 **Технические неполадки** - баги, проблемы с ботами\n"
                   "❓ **Другой вопрос** - все остальное\n\n"
                   "После выбора будет создан приватный канал.",
        color=discord.Color.blue()
    )
    embed.set_footer(text="Меню всегда активно - можно создавать сколько угодно тикетов")
    
    await ctx.send(embed=embed, view=TicketPanelView())
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def app(ctx):
    """Создание панели подачи заявлений"""
    embed = discord.Embed(
        title="📋 Подача заявления в команду",
        description="Хотите стать частью нашей команды?\n\n"
                   "**Доступные должности:**\n"
                   "📹 **Медиа-команда** - создание контента, видео, оформление\n"
                   "🛡️ **Младший модератор** - помощь в модерировании чата\n\n"
                   "Выберите должность ниже и заполните анкету!",
        color=discord.Color.purple()
    )
    embed.set_footer(text="Заявки рассматриваются администрацией")
    
    await ctx.send(embed=embed, view=ApplicationView())
    await ctx.message.delete()

@bot.command()
@commands.has_permissions(administrator=True)
async def add_user(ctx, user: discord.Member):
    """Добавить пользователя в тикет"""
    if ctx.channel.category_id != TICKET_CATEGORY_ID:
        await ctx.send("❌ Команда работает только в каналах тикетов!")
        return
    
    await ctx.channel.set_permissions(user, read_messages=True, send_messages=True)
    await ctx.send(f"✅ {user.mention} добавлен в тикет.")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_user(ctx, user: discord.Member):
    """Удалить пользователя из тикета"""
    if ctx.channel.category_id != TICKET_CATEGORY_ID:
        await ctx.send("❌ Команда работает только в каналах тикетов!")
        return
    
    await ctx.channel.set_permissions(user, overwrite=None)
    await ctx.send(f"✅ {user.mention} удален из тикета.")

@bot.command()
@commands.has_permissions(administrator=True)
async def rename_ticket(ctx, *, new_name: str):
    """Переименовать тикет"""
    if ctx.channel.category_id != TICKET_CATEGORY_ID:
        await ctx.send("❌ Команда работает только в каналах тикетов!")
        return
    
    await ctx.channel.edit(name=new_name)
    await ctx.send(f"✅ Канал переименован в: {new_name}")

@bot.event
async def on_ready():
    print(f"✅ Бот {bot.user} запущен!")
    print(f"📁 Категория тикетов ID: {TICKET_CATEGORY_ID}")
    print(f"👥 STAFF ролей: {len(STAFF_ROLES)}")
    
    bot.add_view(TicketPanelView())
    bot.add_view(ApplicationView())
    
    for channel_id, data in active_tickets.items():
        channel = bot.get_channel(channel_id)
        if channel:
            bot.add_view(TicketControlView(data["user_id"]))

# Запуск бота
if __name__ == "__main__":
    token = os.getenv('DISCORD_BOT_TOKEN')
    if not token:
        print("❌ Ошибка: Не найден токен бота!")
        print("📌 Установите переменную окружения DISCORD_BOT_TOKEN")
        exit(1)
    
    bot.run(token)
